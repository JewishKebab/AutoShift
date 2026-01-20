# app/services/certificates.py
import os
import re
import base64
import json
from typing import Optional, Tuple
import paramiko
from app.services.ssh_vm import run_sudo


def _sh_quote(s: str) -> str:
    return "'" + (s or "").replace("'", "'\"'\"'") + "'"


def _oc(ssh: paramiko.SSHClient, kubeconfig: str, args: str) -> str:
    kc = _sh_quote(kubeconfig)
    return run_sudo(ssh, f"oc --kubeconfig {kc} {args}")


def _sleep(ssh: paramiko.SSHClient, seconds: int) -> None:
    run_sudo(ssh, f"sleep {int(seconds)}")


def _kubeconfig_path(base_dir: str, cluster_dir: str) -> str:
    return f"{base_dir.rstrip('/')}/{cluster_dir}/auth/kubeconfig"


def _cert_dir(base_dir: str, cluster_dir: str) -> str:
    return f"{base_dir.rstrip('/')}/{cluster_dir}/certs"


def _saved_zip_path(base_dir: str, cluster_dir: str) -> str:
    return f"{_cert_dir(base_dir, cluster_dir)}/certs.zip"


def _dump_olm_debug(log, *, ssh: paramiko.SSHClient, kubeconfig: str, operator_ns: str, sub_name: str) -> None:
    def safe(label: str, cmd: str) -> None:
        try:
            out = _oc(ssh, kubeconfig, cmd)
            out = (out or "").strip()
            log(f"[cert][debug] {label}:\n{out if out else '(empty)'}")
        except Exception as e:
            log(f"[cert][debug] {label} failed: {e}")

    safe("subscription yaml", f"-n {operator_ns} get subscription {sub_name} -o yaml 2>&1 || true")
    safe("installplans", f"-n {operator_ns} get installplan 2>&1 || true")
    safe("csv list", f"-n {operator_ns} get csv 2>&1 || true")
    safe("event tail", f"-n {operator_ns} get events --sort-by=.lastTimestamp | tail -n 40 2>&1 || true")
    safe("catalogsources", "-n openshift-marketplace get catalogsource 2>&1 || true")
    safe("marketplace pods", "-n openshift-marketplace get pods 2>&1 || true")


def _packagemanifest_exists(ssh: paramiko.SSHClient, kubeconfig: str, package: str) -> bool:
    # Must not use _oc(... >/dev/null ...) because run_sudo throws on rc!=0.
    try:
        _oc(ssh, kubeconfig, f"-n openshift-marketplace get packagemanifest {package} -o name")
        return True
    except Exception:
        return False


def _pick_cert_manager_package(log, *, ssh: paramiko.SSHClient, kubeconfig: str) -> str:
    candidates = [
        os.environ.get("CERT_MANAGER_PACKAGE", "").strip(),
        "openshift-cert-manager-operator",
        "cert-manager-operator",
        "cert-manager",
    ]
    candidates = [c for c in candidates if c]

    for pkg in candidates:
        if _packagemanifest_exists(ssh, kubeconfig, pkg):
            log(f"[cert] found packagemanifest package={pkg}")
            return pkg

    # last resort: scan all packagemanifests
    raw = _oc(ssh, kubeconfig, "-n openshift-marketplace get packagemanifest -o json").strip()
    if raw:
        try:
            data = json.loads(raw)
            items = data.get("items") or []
            for it in items:
                n = ((it.get("metadata") or {}).get("name") or "").strip()
                if "cert-manager" in n:
                    log(f"[cert] found packagemanifest by scan: {n}")
                    return n
        except Exception:
            pass

    raise RuntimeError("No cert-manager related packagemanifest found in openshift-marketplace")


def _detect_channel(log, *, ssh: paramiko.SSHClient, kubeconfig: str, package: str) -> str:
    raw = _oc(ssh, kubeconfig, f"-n openshift-marketplace get packagemanifest {package} -o json")
    data = json.loads(raw)

    channels = [c.get("name") for c in (data.get("status", {}).get("channels") or []) if c.get("name")]
    default_channel = (data.get("status", {}).get("defaultChannel") or "").strip()

    log(f"[cert] packagemanifest {package}: defaultChannel={default_channel or '(none)'} channels={channels}")

    if "stable" in channels:
        return "stable"
    stable_like = [c for c in channels if c.startswith("stable")]
    if stable_like:
        return stable_like[0]
    if default_channel and default_channel in channels:
        return default_channel
    if channels:
        return channels[0]
    raise RuntimeError(f"No channels found for {package}")


def _apply_subscription(
    *,
    ssh: paramiko.SSHClient,
    kubeconfig: str,
    operator_ns: str,
    subscription_name: str,
    package: str,
    channel: str,
    source: str,
    source_ns: str,
) -> None:
    sub_manifest = f"""\
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: {subscription_name}
  namespace: {operator_ns}
spec:
  channel: {channel}
  name: {package}
  source: {source}
  sourceNamespace: {source_ns}
  installPlanApproval: Automatic
"""
    cmd = (
        "set -euo pipefail; "
        f"oc --kubeconfig {_sh_quote(kubeconfig)} apply -f - <<'YAML'\n{sub_manifest}\nYAML\n"
    )
    run_sudo(ssh, cmd)


def _wait_for_subscription_csv(
    log,
    *,
    ssh: paramiko.SSHClient,
    kubeconfig: str,
    operator_ns: str,
    subscription_name: str,
    timeout_seconds: int,
) -> Optional[str]:
    waited = 0
    step = 10

    while waited < timeout_seconds:
        csv = _oc(
            ssh,
            kubeconfig,
            f"-n {operator_ns} get subscription {subscription_name} -o jsonpath='{{.status.currentCSV}}' 2>/dev/null || true",
        ).strip()
        state = _oc(
            ssh,
            kubeconfig,
            f"-n {operator_ns} get subscription {subscription_name} -o jsonpath='{{.status.state}}' 2>/dev/null || true",
        ).strip()

        log(f"[cert] subscription {subscription_name} state={state or '(unknown)'} currentCSV={csv or '(none)'}")

        if csv:
            return csv

        _sleep(ssh, step)
        waited += step

    return None


def _wait_for_csv_succeeded(
    log,
    *,
    ssh: paramiko.SSHClient,
    kubeconfig: str,
    operator_ns: str,
    csv_name: str,
    timeout_seconds: int,
) -> bool:
    waited = 0
    step = 10
    while waited < timeout_seconds:
        phase = _oc(
            ssh,
            kubeconfig,
            f"-n {operator_ns} get csv {csv_name} -o jsonpath='{{.status.phase}}' 2>/dev/null || true",
        ).strip()
        log(f"[cert] csv {csv_name} phase={phase or '(unknown)'}")
        if phase == "Succeeded":
            return True
        _sleep(ssh, step)
        waited += step
    return False


def _wait_for_crds(
    log,
    *,
    ssh: paramiko.SSHClient,
    kubeconfig: str,
    timeout_seconds: int = 600,
) -> bool:
    waited = 0
    step = 10
    while waited < timeout_seconds:
        try:
            _oc(
                ssh,
                kubeconfig,
                "get crd certificates.cert-manager.io clusterissuers.cert-manager.io issuers.cert-manager.io >/dev/null 2>&1",
            )
            log("[cert] cert-manager CRDs present")
            return True
        except Exception:
            pass
        _sleep(ssh, step)
        waited += step
    log("[cert][error] timed out waiting for cert-manager CRDs")
    return False


def _install_cert_manager_operator(
    log,
    *,
    ssh: paramiko.SSHClient,
    kubeconfig: str,
    operator_ns: str = "openshift-operators",
    subscription_name: str = "openshift-cert-manager-operator",
    source: str = "redhat-operators",
    source_ns: str = "openshift-marketplace",
    timeout_seconds: int = 900,
) -> bool:
    log("[cert] installing cert-manager operator (OLM)...")

    try:
        package = _pick_cert_manager_package(log, ssh=ssh, kubeconfig=kubeconfig)
        channel = _detect_channel(log, ssh=ssh, kubeconfig=kubeconfig, package=package)
    except Exception as e:
        log(f"[cert][error] could not resolve packagemanifest/channel: {e}")
        return False

    log(f"[cert] applying Subscription name={subscription_name} package={package} channel={channel} source={source}/{source_ns}")

    try:
        _apply_subscription(
            ssh=ssh,
            kubeconfig=kubeconfig,
            operator_ns=operator_ns,
            subscription_name=subscription_name,
            package=package,
            channel=channel,
            source=source,
            source_ns=source_ns,
        )
    except Exception as e:
        log(f"[cert][error] failed applying Subscription: {e}")
        _dump_olm_debug(log, ssh=ssh, kubeconfig=kubeconfig, operator_ns=operator_ns, sub_name=subscription_name)
        return False

    csv = _wait_for_subscription_csv(
        log,
        ssh=ssh,
        kubeconfig=kubeconfig,
        operator_ns=operator_ns,
        subscription_name=subscription_name,
        timeout_seconds=timeout_seconds,
    )
    if not csv:
        log("[cert][error] subscription never reported currentCSV (ResolutionFailed/blocked)")
        _dump_olm_debug(log, ssh=ssh, kubeconfig=kubeconfig, operator_ns=operator_ns, sub_name=subscription_name)
        return False

    log(f"[cert] subscription currentCSV={csv}")

    if not _wait_for_csv_succeeded(
        log,
        ssh=ssh,
        kubeconfig=kubeconfig,
        operator_ns=operator_ns,
        csv_name=csv,
        timeout_seconds=timeout_seconds,
    ):
        log("[cert][error] operator CSV did not reach Succeeded")
        _dump_olm_debug(log, ssh=ssh, kubeconfig=kubeconfig, operator_ns=operator_ns, sub_name=subscription_name)
        return False

    if not _wait_for_crds(log, ssh=ssh, kubeconfig=kubeconfig, timeout_seconds=600):
        _dump_olm_debug(log, ssh=ssh, kubeconfig=kubeconfig, operator_ns=operator_ns, sub_name=subscription_name)
        return False

    log("[cert] cert-manager operator installed and CRDs ready")
    return True


def ensure_cert_manager_ready(
    log,
    *,
    ssh: paramiko.SSHClient,
    kubeconfig: str,
    cert_ns: str,
    timeout_seconds: int = 900,
) -> bool:
    log("[cert] checking cert-manager presence...")

    try:
        _oc(
            ssh,
            kubeconfig,
            "get crd certificates.cert-manager.io clusterissuers.cert-manager.io issuers.cert-manager.io >/dev/null 2>&1",
        )
        log("[cert] cert-manager CRDs found")
    except Exception:
        log("[cert] cert-manager CRDs missing -> installing operator")
        if not _install_cert_manager_operator(log, ssh=ssh, kubeconfig=kubeconfig, timeout_seconds=timeout_seconds):
            return False

    try:
        _oc(ssh, kubeconfig, f"get ns {cert_ns} >/dev/null 2>&1")
        log(f"[cert] namespace exists: {cert_ns}")
    except Exception:
        log(f"[cert] creating namespace: {cert_ns}")
        try:
            _oc(ssh, kubeconfig, f"create ns {cert_ns} >/dev/null 2>&1 || true")
        except Exception as e:
            log(f"[cert][error] failed creating namespace {cert_ns}: {e}")
            return False

    try:
        log(f"[cert] waiting for cert-manager pods Ready in {cert_ns} (timeout 300s)...")
        _oc(ssh, kubeconfig, f"-n {cert_ns} wait --for=condition=Ready pod --all --timeout=300s")
        log("[cert] cert-manager pods Ready")
    except Exception as e:
        log(f"[cert][warn] cert-manager pods not all Ready yet: {e}")

    return True


def create_cluster_certificates(
    log,
    *,
    ssh: paramiko.SSHClient,
    cluster_name: str,
    base_dir: str,
    cluster_dir: str,
) -> bool:
    kubeconfig = _kubeconfig_path(base_dir, cluster_dir)
    cert_ns = os.environ.get("CERT_MANAGER_NS", "cert-manager")
    base_domain = os.environ["OCP_BASE_DOMAIN"]

    openshift_domain = f"{cluster_name}-openshift.{base_domain}"

    if not ensure_cert_manager_ready(log, ssh=ssh, kubeconfig=kubeconfig, cert_ns=cert_ns):
        log("[cert] cert-manager not ready; skipping certs")
        return False

    selfsigned_name = f"{cluster_name}-selfsigned"

    manifests = f"""\
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {selfsigned_name}
spec:
  selfSigned: {{}}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: bsmch-ca-cert
  namespace: {cert_ns}
spec:
  issuerRef:
    name: {selfsigned_name}
    kind: ClusterIssuer
  secretName: bsmch-ca-cert
  isCA: true
  commonName: bsmch-ca
  dnsNames:
    - "*.{base_domain}"
    - "*.apps.{openshift_domain}"
    - "api.{openshift_domain}"
  duration: 876600h0m0s
  encodeUsagesInRequest: true
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: bsmch-ca-issuer
spec:
  ca:
    secretName: bsmch-ca-cert
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: bsmch-ingress-cert
  namespace: openshift-ingress
spec:
  issuerRef:
    name: bsmch-ca-issuer
    kind: ClusterIssuer
  secretName: bsmch-ingress-cert
  dnsNames:
    - "*.apps.{openshift_domain}"
"""

    log("[cert] applying certificate manifests...")
    apply_cmd = (
        "set -euo pipefail; "
        f"oc --kubeconfig {_sh_quote(kubeconfig)} apply -f - <<'YAML'\n{manifests}\nYAML\n"
    )
    try:
        run_sudo(ssh, apply_cmd)
    except Exception as e:
        log(f"[cert][error] apply failed: {e}")
        return False

    log("[cert] waiting for certificates Ready...")
    try:
        _oc(ssh, kubeconfig, f"-n {cert_ns} wait --for=condition=Ready certificate/bsmch-ca-cert --timeout=600s")
        _oc(ssh, kubeconfig, "-n openshift-ingress wait --for=condition=Ready certificate/bsmch-ingress-cert --timeout=600s")
    except Exception as e:
        log(f"[cert][error] wait failed: {e}")
        return False

    log("[cert] patching ingresscontroller default certificate...")
    try:
        patch = '{"spec":{"defaultCertificate":{"name":"bsmch-ingress-cert"}}}'
        _oc(
            ssh,
            kubeconfig,
            f"patch ingresscontroller.operator default -n openshift-ingress-operator --type=merge --patch {_sh_quote(patch)}",
        )
    except Exception as e:
        log(f"[cert][error] ingress patch failed: {e}")
        return False

    cert_dir = _cert_dir(base_dir, cluster_dir)
    zip_path = _saved_zip_path(base_dir, cluster_dir)

    log(f"[cert] exporting certs to VM: {zip_path}")
    try:
        run_sudo(ssh, f"set -euo pipefail; mkdir -p {_sh_quote(cert_dir)}; chmod 700 {_sh_quote(cert_dir)}")

        # ensure zip exists (CentOS 8 might use dnf)
        run_sudo(ssh, "command -v zip >/dev/null 2>&1 || (dnf -y install zip >/dev/null 2>&1 || yum -y install zip >/dev/null 2>&1 || true)")

        # IMPORTANT: correct jsonpath (single braces) and quote it with single-quotes
        write_ca = (
            "set -euo pipefail; "
            f"oc --kubeconfig {_sh_quote(kubeconfig)} -n {cert_ns} get secret/bsmch-ca-cert "
            f"-o jsonpath='{ '{.data.ca\\.crt}' }' | base64 -d > {_sh_quote(cert_dir)}/ca.crt"
        )
        write_ing = (
            "set -euo pipefail; "
            f"oc --kubeconfig {_sh_quote(kubeconfig)} -n openshift-ingress get secret/bsmch-ingress-cert "
            f"-o jsonpath='{ '{.data.tls\\.crt}' }' | base64 -d > {_sh_quote(cert_dir)}/ingress.crt"
        )

        run_sudo(ssh, write_ca)
        run_sudo(ssh, write_ing)

        run_sudo(ssh, f"set -euo pipefail; cd {_sh_quote(cert_dir)}; zip -q -r certs.zip ca.crt ingress.crt")
        run_sudo(ssh, f"chmod 600 {_sh_quote(cert_dir)}/ca.crt {_sh_quote(cert_dir)}/ingress.crt {_sh_quote(zip_path)}")
        log(f"[cert] cert bundle saved: {zip_path}")
    except Exception as e:
        log(f"[cert][error] failed saving certs: {e}")
        return False

    log("[cert] done")
    return True


def build_certs_zip_bytes(
    *,
    ssh: paramiko.SSHClient,
    base_dir: str,
    cluster_dir: str,
) -> Tuple[bool, Optional[bytes], str]:
    zip_path = _saved_zip_path(base_dir, cluster_dir)
    try:
        run_sudo(ssh, f"test -f {_sh_quote(zip_path)}")
    except Exception as e:
        return False, None, f"cert bundle not found on VM: {zip_path} ({e})"

    try:
        b64 = run_sudo(ssh, f"base64 -w0 {_sh_quote(zip_path)}")
        if not (b64 or "").strip():
            return False, None, "cert zip is empty"
        return True, base64.b64decode(b64), ""
    except Exception as e:
        return False, None, f"failed to read cert zip: {e}"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _sh_quote(s: str) -> str:
    return "'" + (s or "").replace("'", "'\"'\"'") + "'"


def normalize_cluster_base(name: str) -> str:
    """
    Converts anything into the base you use for folders:
      az-<base>-cluster

    Examples:
      testcert -> testcert
      testcert-openshift -> testcert
      az-testcert-cluster -> testcert
      az-testcert-openshift-cluster -> testcert
    """
    s = (name or "").strip().lower()
    s = s.replace("\\", "/")
    if "/" in s:
        s = s.split("/")[-1].strip()

    if s.startswith("az-"):
        s = s[len("az-"):]
    if s.endswith("-cluster"):
        s = s[: -len("-cluster")]
    if s.endswith("-openshift"):
        s = s[: -len("-openshift")]
    while s.endswith("-openshift-openshift"):
        s = s[: -len("-openshift")]

    s = s.strip("-")
    return s or "cluster"


def _zip_path(base_dir: str, cluster_dir: str) -> str:
    return f"{base_dir.rstrip('/')}/{cluster_dir}/certs/certs.zip"


def cert_zip_exists_on_vm(*, ssh: paramiko.SSHClient, base_dir: str, cluster_dir: str) -> bool:
    zip_path = _zip_path(base_dir, cluster_dir)
    try:
        run_sudo(ssh, f"test -f {_sh_quote(zip_path)}")
        return True
    except Exception:
        return False


def read_cert_zip_from_vm(
    *, ssh: paramiko.SSHClient, base_dir: str, cluster_dir: str
) -> Tuple[bool, Optional[bytes], str]:
    zip_path = _zip_path(base_dir, cluster_dir)

    try:
        run_sudo(ssh, f"test -f {_sh_quote(zip_path)}")
    except Exception as e:
        return False, None, f"cert zip not found at {zip_path}: {e}"

    try:
        # Use base64 to transport binary over stdout
        b64 = run_sudo(ssh, f"base64 -w0 {_sh_quote(zip_path)}")
        b64 = (b64 or "").strip()
        if not b64:
            return False, None, "cert zip is empty"
        return True, base64.b64decode(b64), ""
    except Exception as e:
        return False, None, f"failed reading cert zip: {e}"
