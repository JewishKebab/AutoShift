import time
import requests
import jwt
from jwt.algorithms import RSAAlgorithm

_jwks_cache = {"keys": None, "fetched_at": 0}

def _get_openid_config(tenant_id: str) -> dict:
    url = f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
    return requests.get(url, timeout=10).json()

def _get_jwks(jwks_uri: str) -> dict:
    now = int(time.time())
    # cache for 6 hours
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < 21600:
        return _jwks_cache["keys"]

    keys = requests.get(jwks_uri, timeout=10).json()
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys

def validate_bearer_token(token: str, tenant_id: str, audience: str, issuer: str | None = None) -> dict:
    oidc = _get_openid_config(tenant_id)
    jwks = _get_jwks(oidc["jwks_uri"])

    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    if not kid:
        raise ValueError("Token header missing kid")

    key = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
    if not key:
        raise ValueError("Signing key not found")

    public_key = RSAAlgorithm.from_jwk(key)

    # issuer for v2 tokens typically like: https://login.microsoftonline.com/<tenant_id>/v2.0
    expected_issuer = issuer or f"https://login.microsoftonline.com/{tenant_id}/v2.0"

    claims = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience=audience,
        issuer=expected_issuer,
        options={"verify_signature": True, "verify_aud": True, "verify_iss": True},
    )
    return claims
