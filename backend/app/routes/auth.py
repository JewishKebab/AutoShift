import os
import msal
from datetime import timedelta
from flask import Blueprint, jsonify, redirect, request, make_response, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    set_access_cookies,
    set_refresh_cookies,
)
from app.auth.azure_config import AzureConfig

bp = Blueprint("auth", __name__, url_prefix="/api")
azure_config = AzureConfig()

# This must match the **App Role VALUE** in Entra ID exactly
REQUIRED_AZURE_ROLE = "User"


def map_azure_role_to_app_role(azure_roles: list[str]) -> str:
    if REQUIRED_AZURE_ROLE in azure_roles:
        return "user"
    return "guest"


def get_frontend_url() -> str:
    """
    Resolve frontend URL from environment.
    Falls back to localhost for dev.
    Always returns a clean, non-empty URL.
    """
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080").strip()

    if not frontend_url:
        raise RuntimeError("FRONTEND_URL environment variable is not set")

    return frontend_url.rstrip("/")


@bp.get("/login/azure")
def azure_login():
    msal_app = msal.ConfidentialClientApplication(
        azure_config.CLIENT_ID,
        authority=azure_config.AUTHORITY,
        client_credential=azure_config.CLIENT_SECRET,
    )

    auth_url = msal_app.get_authorization_request_url(
        scopes=azure_config.SCOPE,
        redirect_uri=azure_config.REDIRECT_URI,
    )

    return jsonify({"auth_url": auth_url}), 200


@bp.get("/login/azure/callback")
def azure_callback():
    # Azure returned an error
    if "error" in request.args:
        return jsonify(
            {
                "ok": False,
                "error": request.args.get(
                    "error_description", "Azure auth failed"
                ),
            }
        ), 400

    code = request.args.get("code")
    if not code:
        return jsonify(
            {"ok": False, "error": "No authorization code provided"}
        ), 400

    msal_app = msal.ConfidentialClientApplication(
        azure_config.CLIENT_ID,
        authority=azure_config.AUTHORITY,
        client_credential=azure_config.CLIENT_SECRET,
    )

    token_response = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=azure_config.SCOPE,
        redirect_uri=azure_config.REDIRECT_URI,
    )

    if not token_response:
        return jsonify(
            {"ok": False, "error": "Failed to acquire token from Azure"}
        ), 400

    if "error" in token_response:
        return jsonify(
            {
                "ok": False,
                "error": token_response.get("error_description")
                or token_response.get("error")
                or "Failed to acquire token from Azure",
            }
        ), 400

    claims = token_response.get("id_token_claims") or {}
    user_id = claims.get("oid") or claims.get("sub")
    email = claims.get("preferred_username") or claims.get("email")
    name = claims.get("name", "")
    azure_roles = claims.get("roles", []) or []

    frontend_url = get_frontend_url()

    # HARD GATE: must have the User app role
    if REQUIRED_AZURE_ROLE not in azure_roles:
        current_app.logger.warning(
            "Blocked login: missing required role '%s' for user '%s'. roles=%s",
            REQUIRED_AZURE_ROLE,
            email or user_id,
            azure_roles,
        )
        return redirect(f"{frontend_url}/unauthorized")

    app_role = map_azure_role_to_app_role(azure_roles)

    token_claims = {
        "role": app_role,
        "azure_roles": azure_roles,
        "email": email,
        "name": name,
        "auth_source": "azure",
    }

    access_jwt = create_access_token(
        identity=user_id,
        additional_claims=token_claims,
        expires_delta=timedelta(hours=1),
    )
    refresh_jwt = create_refresh_token(
        identity=user_id,
        additional_claims=token_claims,
        expires_delta=timedelta(days=30),
    )

    response = make_response(redirect(f"{frontend_url}/dashboard"))
    set_access_cookies(response, access_jwt)
    set_refresh_cookies(response, refresh_jwt)
    return response

