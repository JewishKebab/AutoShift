import os
from datetime import timedelta


class Config:
    # Flask
    SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret")
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

    # Azure / OCP automation env vars
    AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
    AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
    AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
    SUBSCRIPTION_ID = os.getenv("SUBSCRIPTION_ID", "")

    AZ_RESOURCE_GROUP = os.getenv("AZ_RESOURCE_GROUP", "")
    AZ_VNET_NAME = os.getenv("AZ_VNET_NAME", "")
    AZ_SUBNET_PREFIX = os.getenv("AZ_SUBNET_PREFIX", "10.104")
    AZ_SUBNET_PREFIXLEN = os.getenv("AZ_SUBNET_PREFIXLEN", "22")
    POLICY_ASSIGNMENT_ID = os.getenv("POLICY_ASSIGNMENT_ID", "")

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")

    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_ACCESS_COOKIE_NAME = "access_token_cookie"
    JWT_REFRESH_COOKIE_NAME = "refresh_token_cookie"

    JWT_COOKIE_SECURE = False          
    JWT_COOKIE_SAMESITE = "Lax"       
    JWT_COOKIE_CSRF_PROTECT = False    
    