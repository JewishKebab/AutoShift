// src/components/clusters/CreateClusterForm/ClusterConfigurationCard.tsx
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { CheckCircle2, Loader2, Network, Rocket, Search } from 'lucide-react';
import type { SuggestedSubnets } from './types';

type VmSize = { label: string; value: string };

type Props = {
  name: string;
  setName: (v: string) => void;

  //  NEW: resolved "<name>-openshift"
  resolvedName: string;

  vmSizes: VmSize[];

  masterNodeSize: string;
  setMasterNodeSize: (v: string) => void;
  workerNodeSize: string;
  setWorkerNodeSize: (v: string) => void;

  masterReplicas: number;
  setMasterReplicas: (v: number) => void;
  workerReplicas: number;
  setWorkerReplicas: (v: number) => void;

  isSearchingSubnets: boolean;
  subnetsFound: boolean;
  suggestedSubnets: SuggestedSubnets | null;

  onFindSubnets: () => void;

  isCreating: boolean;
  onCreateCluster: () => void;
};

export function ClusterConfigurationCard(props: Props) {
  const {
    name,
    setName,
    resolvedName,
    vmSizes,
    masterNodeSize,
    setMasterNodeSize,
    workerNodeSize,
    setWorkerNodeSize,
    masterReplicas,
    setMasterReplicas,
    workerReplicas,
    setWorkerReplicas,
    isSearchingSubnets,
    subnetsFound,
    suggestedSubnets,
    onFindSubnets,
    isCreating,
    onCreateCluster,
  } = props;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Network className="h-5 w-5 text-primary" />
          Cluster Configuration
        </CardTitle>
        <CardDescription>Enter the cluster details and find available subnets</CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        <div className="space-y-2">
          <Label htmlFor="cluster-name">Cluster Name</Label>
          <Input
            id="cluster-name"
            placeholder="e.g., monitoring"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />

          <p className="text-xs text-muted-foreground">
            Will be created as:{' '}
            {resolvedName ? <span className="font-mono">{resolvedName}</span> : '...'}
          </p>

          <p className="text-xs text-muted-foreground">
            Subnet Names:{' '}
            {resolvedName ? (
              <span className="font-mono">
                {resolvedName}-master-subnet, {resolvedName}-worker-subnet
              </span>
            ) : (
              '...'
            )}
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Master Node Size</Label>
            <Select value={masterNodeSize} onValueChange={setMasterNodeSize}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {vmSizes.map((size) => (
                  <SelectItem key={size.value} value={size.value}>
                    {size.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Master Replicas</Label>
            <Select value={masterReplicas.toString()} onValueChange={(v) => setMasterReplicas(parseInt(v, 10))}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="3">3 (Recommended)</SelectItem>
                <SelectItem value="5">5</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Worker Node Size</Label>
            <Select value={workerNodeSize} onValueChange={setWorkerNodeSize}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {vmSizes.map((size) => (
                  <SelectItem key={size.value} value={size.value}>
                    {size.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">Includes Standard_F8s</p>
          </div>

          <div className="space-y-2">
            <Label>Worker Replicas</Label>
            <Select value={workerReplicas.toString()} onValueChange={(v) => setWorkerReplicas(parseInt(v, 10))}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="2">2</SelectItem>
                <SelectItem value="3">3 (Recommended)</SelectItem>
                <SelectItem value="4">4</SelectItem>
                <SelectItem value="5">5</SelectItem>
                <SelectItem value="6">6</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="pt-2">
          <Button
            onClick={onFindSubnets}
            disabled={!resolvedName || isSearchingSubnets}
            variant="secondary"
            className="w-full md:w-auto gap-2"
          >
            {isSearchingSubnets ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Searching for Subnets...
              </>
            ) : (
              <>
                <Search className="h-4 w-4" />
                Find Subnets
              </>
            )}
          </Button>
        </div>

        {subnetsFound && suggestedSubnets && (
          <Card className="border-success/50 bg-success/5 animate-fade-in">
            <CardContent className="pt-4">
              <div className="flex items-start gap-3">
                <CheckCircle2 className="h-5 w-5 text-success mt-0.5" />
                <div className="space-y-3">
                  <p className="font-medium text-success">Found suitable subnets in VNet!</p>

                  <div className="text-sm space-y-2 bg-background/50 rounded-md p-3 font-mono">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Master Subnet:</span>
                      <span className="font-medium">{suggestedSubnets.master}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">CIDR:</span>
                      <span className="font-medium text-primary">{suggestedSubnets.masterCidr}</span>
                    </div>
                    <div className="border-t border-border my-2" />
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Worker Subnet:</span>
                      <span className="font-medium">{suggestedSubnets.worker}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">CIDR:</span>
                      <span className="font-medium text-primary">{suggestedSubnets.workerCidr}</span>
                    </div>
                  </div>

                  <p className="text-xs text-muted-foreground">VNet: SharedServices-Bsmch-Prod-Openshift-VNet</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="pt-4 border-t">
          <Button
            onClick={onCreateCluster}
            disabled={!subnetsFound || isCreating}
            className="w-full gap-2 gradient-openshift text-primary-foreground"
            size="lg"
          >
            {isCreating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Initiating Cluster Creation...
              </>
            ) : (
              <>
                <Rocket className="h-4 w-4" />
                Create Cluster
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
