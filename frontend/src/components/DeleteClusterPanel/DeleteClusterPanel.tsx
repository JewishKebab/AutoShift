import { useMemo, useState } from "react";
import { toast } from "sonner";
import { useClusters } from "@/contexts/ClusterContext";
import { ClusterCard } from "./DeleteClusterCard";
import { Trash2, AlertTriangle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

import { destroyCluster } from "@/lib/api";
import { useInstallerLogs } from "@/components/CreateClusterForm/useInstallerLogs";
import { InstallerLogsCard } from "@/components/CreateClusterForm/InstallerLogsCard";

export function DeleteClusterPanel() {
  const { azureClusters } = useClusters();
  const [busyClusterId, setBusyClusterId] = useState<string | null>(null);

  // logs hook (same one you use for install)
  const logs = useInstallerLogs({ apiBase: "" });

  const deletableClusters = useMemo(() => {
    const list = [...(azureClusters ?? [])];
    return list.filter((c) => c.status === "running" || c.status === "failed");
  }, [azureClusters]);

  const handleDelete = async (cluster: any) => {
    setBusyClusterId(cluster.id);

    try {
      const clusterName = String(cluster.name || "").trim();
      if (!clusterName) throw new Error("Cluster name missing");

      // 1) start destroy
      const res = await destroyCluster(clusterName);

      toast.success("Destroy started", { description: `Job: ${res.jobId}` });

      // 2) show logs + stream
      logs.actions.setInstallLogs([]);
      logs.actions.setPersistedCursor(0);
      await logs.actions.startLogStream(res.jobId);
    } catch (e: any) {
      toast.error("Destroy failed to start", { description: e?.message || String(e) });
    } finally {
      setBusyClusterId(null);
    }
  };

  const isBusy = busyClusterId !== null;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="font-display text-2xl font-bold tracking-tight">Delete Cluster</h2>
        <p className="text-muted-foreground mt-1">
          Remove OpenShift clusters and their associated resources
        </p>
      </div>

      <Alert variant="destructive" className="border-destructive/50 bg-destructive/10">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Warning</AlertTitle>
        <AlertDescription>
          Deleting a cluster will remove all associated subnets, resources, and data.
          This action cannot be undone.
        </AlertDescription>
      </Alert>

      <div className="space-y-4">
        <h3 className="font-display text-lg font-semibold">Available for Deletion</h3>

        {deletableClusters.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <Trash2 className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>No clusters available for deletion</p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {deletableClusters.map((cluster) => (
              <ClusterCard
                key={cluster.id}
                cluster={cluster}
                onDelete={() => handleDelete(cluster)}
                isBusy={isBusy}
                isThisBusy={busyClusterId === cluster.id}
              />
            ))}
          </div>
        )}
      </div>

      {/* ✅ logs for destroy jobs show up here */}
      {logs.state.installJobId && (
        <InstallerLogsCard
          installJobId={logs.state.installJobId}
          installLogs={logs.state.installLogs}
          isInstalling={logs.state.isInstalling}
          logsExpanded={logs.state.logsExpanded}
          setLogsExpanded={logs.actions.setLogsExpanded}
          autoScroll={logs.state.autoScroll}
          setAutoScroll={logs.actions.setAutoScroll}
          maxLines={logs.state.maxLines}
          setMaxLines={logs.actions.setMaxLines}
          onClear={() => logs.actions.setInstallLogs([])}
          logBoxRef={logs.ui.logBoxRef}
          isUserAtBottom={logs.ui.isUserAtBottom}
          scrollToBottom={logs.ui.scrollToBottom}
        />
      )}
    </div>
  );
}
