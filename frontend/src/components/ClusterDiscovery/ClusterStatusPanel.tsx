import { useClusters } from '@/contexts/ClusterContext';
import { ClusterCard } from './ClusterCard';
import { Server, Loader2, CheckCircle2, XCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function ClusterStatusPanel() {
  const { azureClusters, isInitialLoading, isRefreshing, refresh, lastUpdatedAt } = useClusters();

  const runningClusters = azureClusters.filter((c) => c.status === 'running');
  const deployingClusters = azureClusters.filter((c) => c.status === 'deploying' || c.status === 'pending');
  const failedClusters = azureClusters.filter((c) => c.status === 'failed');

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl font-bold tracking-tight">Cluster Status</h2>
          <p className="text-muted-foreground mt-1">Monitor all your OpenShift clusters</p>
          {lastUpdatedAt && (
            <p className="text-xs text-muted-foreground mt-1">
              Last updated: {new Date(lastUpdatedAt).toLocaleTimeString()}
            </p>
          )}
        </div>

          <Button variant="secondary" size="sm" onClick={refresh} disabled={isRefreshing} className="gap-2">
    {isRefreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
    Refresh
</Button>
      </div>

      {/* Stats Overview */}
      <div className="grid gap-4 md:grid-cols-3">
        <div className="bg-card rounded-lg p-4 border flex items-center gap-4">
          <div className="p-3 rounded-full bg-success/10">
            <CheckCircle2 className="h-6 w-6 text-success" />
          </div>
          <div>
            <p className="text-2xl font-bold font-display">{runningClusters.length}</p>
            <p className="text-sm text-muted-foreground">Running</p>
          </div>
        </div>

        <div className="bg-card rounded-lg p-4 border flex items-center gap-4">
          <div className="p-3 rounded-full bg-warning/10">
            <Loader2 className={`h-6 w-6 text-warning ${isRefreshing ? 'animate-spin' : ''}`} />
          </div>
          <div>
            <p className="text-2xl font-bold font-display">{deployingClusters.length}</p>
            <p className="text-sm text-muted-foreground">Deploying / Pending</p>
          </div>
        </div>

        <div className="bg-card rounded-lg p-4 border flex items-center gap-4">
          <div className="p-3 rounded-full bg-destructive/10">
            <XCircle className="h-6 w-6 text-destructive" />
          </div>
          <div>
            <p className="text-2xl font-bold font-display">{failedClusters.length}</p>
            <p className="text-sm text-muted-foreground">Failed</p>
          </div>
        </div>
      </div>

      {/* Loading state */}
      {(isInitialLoading || (isRefreshing && azureClusters.length === 0)) && (
        <div className="text-center py-12 text-muted-foreground">
          <Loader2 className="h-12 w-12 mx-auto mb-4 animate-spin opacity-40" />
          <p>Loading clusters…</p>
        </div>
      )}

      {/* Deploying Clusters */}
      {deployingClusters.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-display text-lg font-semibold flex items-center gap-2">
            <Loader2 className="h-5 w-5 text-warning animate-spin" />
            Deploying / Pending
          </h3>
          <div className="grid gap-4 md:grid-cols-2">
            {deployingClusters.map((cluster) => (
              <ClusterCard key={cluster.id} cluster={cluster} />
            ))}
          </div>
        </div>
      )}

      {/* Running Clusters */}
      {runningClusters.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-display text-lg font-semibold flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-success" />
            Running
          </h3>
          <div className="grid gap-4 md:grid-cols-2">
            {runningClusters.map((cluster) => (
              <ClusterCard key={cluster.id} cluster={cluster} />
            ))}
          </div>
        </div>
      )}

      {/* Failed Clusters */}
      {failedClusters.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-display text-lg font-semibold flex items-center gap-2">
            <XCircle className="h-5 w-5 text-destructive" />
            Failed
          </h3>
          <div className="grid gap-4 md:grid-cols-2">
            {failedClusters.map((cluster) => (
              <ClusterCard key={cluster.id} cluster={cluster} />
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!isRefreshing && azureClusters.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <Server className="h-12 w-12 mx-auto mb-4 opacity-20" />
          <p>No clusters found</p>
          <p className="text-sm">No matching resource groups in Azure</p>
        </div>
      )}
    </div>
  );
}
