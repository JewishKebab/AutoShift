import os

class AzureConfig:
    def __init__(self):
        # Prefer AZURE_* naming, fallback to TENANT_ID if you already have it
        self.TENANT_ID = os.getenv("AZURE_TENANT_ID") or os.getenv("TENANT_ID")
        self.CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
        self.CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
        self.REDIRECT_URI = os.getenv("AZURE_REDIRECT_URI")

        # Fail fast with clear errors
        if not self.TENANT_ID:
            raise ValueError("Missing AZURE_TENANT_ID (or TENANT_ID) in environment")
        if not self.CLIENT_ID:
            raise ValueError("Missing AZURE_CLIENT_ID in environment")
        if not self.CLIENT_SECRET:
            raise ValueError("Missing AZURE_CLIENT_SECRET in environment")
        if not self.REDIRECT_URI:
            raise ValueError("Missing AZURE_REDIRECT_URI in environment")

        self.AUTHORITY = f"https://login.microsoftonline.com/{self.TENANT_ID}"

        #  MSAL SCOPES: do NOT include openid/profile here
        # Use Graph delegated scope (works in almost every tenant)
        self.SCOPE = ["User.Read"]
