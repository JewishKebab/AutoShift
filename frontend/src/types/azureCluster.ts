export type AzureClusterStatus = 'running' | 'deploying' | 'pending' | 'failed';

export type AzureCluster = {
  id: string;
  name: string; // cluster name from RG prefix
  infra: string; // 5 char suffix
  resourceGroup: string;
  subscriptionId: string;
  status: AzureClusterStatus;

  dnsZone: string;         // <clustername>.bsmch.net
  dnsZoneFound: boolean;
};
