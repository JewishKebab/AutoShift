import { ClusterStatusBadge } from './ClusterStatusBadge';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Server, HardDrive, MapPin, Calendar, Trash2, ExternalLink } from 'lucide-react';
import { useClusters } from '@/contexts/ClusterContext';
import { formatDistanceToNow } from 'date-fns';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';

// Accept both your "old" Cluster shape and the new Azure-discovery shape.
type AnyCluster = {
  id: string;
  name: string;
  status: string;

  // old/local fields (optional)
  baseDomain?: string;
  masterNodeSize?: string;
  workerNodeSize?: string;
  masterReplicas?: number;
  workerReplicas?: number;
  region?: string;
  createdAt?: any;

  // azure fields (optional)
  resourceGroup?: string;
  infra?: string;
  subscriptionId?: string;
  dnsZone?: string;
  dnsZoneFound?: boolean;
};

interface ClusterCardProps {
  cluster: AnyCluster;
}

function vmFamily(size?: string) {
  if (!size) return '—';
  // your old code: "Standard_D8s_v3" -> "D8s" (index 1)
  const parts = size.split('_');
  return parts[1] ?? size;
}

function safeCreatedText(createdAt: any) {
  if (!createdAt) return null;
  try {
    const d = createdAt instanceof Date ? createdAt : new Date(createdAt);
    if (Number.isNaN(d.getTime())) return null;
    return formatDistanceToNow(d, { addSuffix: true });
  } catch {
    return null;
  }
}

export function ClusterCard({ cluster }: ClusterCardProps) {
  const ctx = useClusters() as any;

  // deleteCluster might exist only in your old flow. Keep safe.
  const deleteCluster: undefined | ((id: string) => void) = ctx?.deleteCluster;

  const isDeleting = cluster.status === 'deleting';
  const canDelete = (cluster.status === 'running' || cluster.status === 'failed') && typeof deleteCluster === 'function';

  const hasSizing =
    typeof cluster.masterReplicas === 'number' &&
    typeof cluster.workerReplicas === 'number' &&
    typeof cluster.masterNodeSize === 'string' &&
    typeof cluster.workerNodeSize === 'string';

  const createdText = safeCreatedText(cluster.createdAt);

  return (
    <Card className="animate-fade-in transition-all hover:shadow-lg hover:shadow-primary/5 border-border/50">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <h3 className="font-display font-semibold text-lg leading-none tracking-tight">
              {cluster.name}
            </h3>

            {/* Prefer baseDomain if present, else show dnsZone (azure), else show resourceGroup */}
            <p className="text-sm text-muted-foreground">
              {cluster.baseDomain ?? cluster.dnsZone ?? cluster.resourceGroup ?? ''}
            </p>
          </div>
          <ClusterStatusBadge status={cluster.status} />
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* OLD/local cluster view */}
        {hasSizing ? (
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Server className="h-4 w-4 text-primary" />
              <span>
                Master: {cluster.masterReplicas}x {vmFamily(cluster.masterNodeSize)}
              </span>
            </div>
            <div className="flex items-center gap-2 text-muted-foreground">
              <HardDrive className="h-4 w-4 text-primary" />
              <span>
                Worker: {cluster.workerReplicas}x {vmFamily(cluster.workerNodeSize)}
              </span>
            </div>

            <div className="flex items-center gap-2 text-muted-foreground">
              <MapPin className="h-4 w-4 text-primary" />
              <span className="capitalize">{cluster.region ?? '—'}</span>
            </div>

            <div className="flex items-center gap-2 text-muted-foreground">
              <Calendar className="h-4 w-4 text-primary" />
              <span>{createdText ?? '—'}</span>
            </div>
          </div>
        ) : (
          /* AZURE discovery view */
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Server className="h-4 w-4 text-primary" />
              <span>Infra: {cluster.infra ?? '—'}</span>
            </div>

            <div className="flex items-center gap-2 text-muted-foreground">
              <HardDrive className="h-4 w-4 text-primary" />
              <span>RG: {cluster.resourceGroup ?? '—'}</span>
            </div>

            <div className="flex items-center gap-2 text-muted-foreground">
              <MapPin className="h-4 w-4 text-primary" />
              <span>DNS: {cluster.dnsZone ?? '—'}</span>
            </div>

            <div className="flex items-center gap-2 text-muted-foreground">
              <Calendar className="h-4 w-4 text-primary" />
              <span>Zone: {cluster.dnsZoneFound ? 'found' : 'missing'}</span>
            </div>
          </div>
        )}

        <div className="flex gap-2 pt-2">
          {cluster.status === 'running' && (
            <Button variant="outline" size="sm" className="flex-1 gap-2">
              <ExternalLink className="h-4 w-4" />
              Open Console
            </Button>
          )}

          {canDelete && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm" className="gap-2">
                  <Trash2 className="h-4 w-4" />
                  Delete
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete Cluster</AlertDialogTitle>
                  <AlertDialogDescription>
                    Are you sure you want to delete <strong>{cluster.name}</strong>?
                    This action will remove all associated subnets and resources.
                    This cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => deleteCluster?.(cluster.id)}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    Delete Cluster
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}

          {isDeleting && (
            <Button variant="outline" size="sm" disabled className="gap-2">
              <Trash2 className="h-4 w-4 animate-pulse" />
              Deleting...
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
