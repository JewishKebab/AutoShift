import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getOpenShiftConsoleUrl } from "./consoleUrl";

type Cluster = {
  id: string;
  name: string;
  status: string;
  dnsZone?: string;
  openshiftConsoleUrl?: string;

  // keep any other fields you already use:
  infra?: string;
  resourceGroup?: string;
  subscriptionId?: string;
  certZipFound?: boolean;
  certZipPath?: string;
};

export function ClusterCard({ cluster }: { cluster: Cluster }) {
  const consoleUrl = getOpenShiftConsoleUrl(cluster);

  return (
    <div className="bg-card rounded-lg border p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-display text-lg font-semibold">{cluster.name}</div>
          <div className="text-sm text-muted-foreground">
            Status: <span className="font-medium">{cluster.status}</span>
          </div>
          {cluster.dnsZone && (
            <div className="text-xs text-muted-foreground mt-1">
              DNS: <span className="font-mono">{cluster.dnsZone}</span>
            </div>
          )}
        </div>

        {consoleUrl && (
          <Button asChild size="sm" className="gap-2">
            <a href={consoleUrl} target="_blank" rel="noreferrer">
              Go to OpenShift
              <ExternalLink className="h-4 w-4" />
            </a>
          </Button>
        )}
      </div>

      {/* Optional: cert bundle info if you show it */}
      {cluster.certZipFound && cluster.certZipPath && (
        <div className="text-xs text-muted-foreground">
          Cert bundle: <span className="font-mono">{cluster.certZipPath}</span>
        </div>
      )}
    </div>
  );
}
