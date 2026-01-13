from azure.identity import ClientSecretCredential
from azure.mgmt.network import NetworkManagementClient


def get_network_client(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    subscription_id: str
) -> NetworkManagementClient:
    cred = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )
    return NetworkManagementClient(cred, subscription_id)
