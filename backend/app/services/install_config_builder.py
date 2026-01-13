import os
import yaml

def build_install_config(
    *,
    cluster_name: str,
    master_cidr: str,
    worker_cidr: str,
    master_vm_size: str,
    worker_vm_size: str,
    master_replicas: int,
    worker_replicas: int,
) -> str:
    # Required env vars (fail fast with clear errors)
    base_domain = os.environ["OCP_BASE_DOMAIN"]
    region = os.environ["OCP_REGION"]

    base_domain_rg = os.environ["OCP_BASE_DOMAIN_RG"]
    network_rg = os.environ["OCP_NETWORK_RG"]
    vnet_name = os.environ["OCP_VNET_NAME"]

    pull_secret = os.environ["OCP_PULL_SECRET"]
    ssh_pubkey = os.environ["OCP_SSH_PUBKEY"]

    doc = {
        "apiVersion": "v1",
        "metadata": {"name": f"{cluster_name}-openshift"},
        "baseDomain": base_domain,
        "controlPlane": {
            "hyperthreading": "Enabled",
            "name": "master",
            "replicas": master_replicas,
            "platform": {
                "azure": {
                    "osDisk": {"diskSizeGB": 512},
                    "type": master_vm_size,
                }
            },
        },
        "compute": [
            {
                "hyperthreading": "Enabled",
                "name": "worker",
                "replicas": worker_replicas,
                "platform": {
                    "azure": {
                        "type": worker_vm_size,
                        "osDisk": {"diskSizeGB": 512},
                    }
                },
            }
        ],
        "networking": {
            "networkType": "OVNKubernetes",
            "clusterNetwork": [{"cidr": "10.128.0.0/14", "hostPrefix": 23}],
            "machineNetwork": [{"cidr": master_cidr}, {"cidr": worker_cidr}],
            "serviceNetwork": ["172.30.0.0/16"],
        },
        "platform": {
            "azure": {
                "baseDomainResourceGroupName": base_domain_rg,
                "cloudName": "AzurePublicCloud",
                "region": region,
                "networkResourceGroupName": network_rg,
                "virtualNetwork": vnet_name,
                "controlPlaneSubnet": f"{cluster_name}-master-subnet",
                "computeSubnet": f"{cluster_name}-worker-subnet",
            }
        },
        "pullSecret": pull_secret,
        "sshKey": ssh_pubkey,
        "publish": "Internal",
    }

    return yaml.safe_dump(doc, sort_keys=False)
