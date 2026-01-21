export function getOpenShiftConsoleUrl(cluster: {
  openshiftConsoleUrl?: string;
  dnsZone?: string;
}): string | null {
  if (cluster.openshiftConsoleUrl) return cluster.openshiftConsoleUrl;

  const z = (cluster.dnsZone || "").trim().replace(/\.$/, "");
  if (!z) return null;

  return `https://console-openshift-console.apps.${z}/`;
}
