import { AzureClusterStatus } from '@/types/azureCluster';
import { Badge } from '@/components/ui/badge';
import { Loader2, CheckCircle2, XCircle, Clock, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ClusterStatusBadgeProps {
  status: AzureClusterStatus;
  className?: string;
}

const statusConfig: Record<AzureClusterStatus, { 
  label: string; 
  icon: React.ElementType;
  variant: 'default' | 'secondary' | 'destructive' | 'outline';
  className: string;
}> = {
  running: {
    label: 'Running',
    icon: CheckCircle2,
    variant: 'default',
    className: 'bg-success text-success-foreground hover:bg-success/90',
  },
  deploying: {
    label: 'Deploying',
    icon: Loader2,
    variant: 'secondary',
    className: 'bg-warning text-warning-foreground hover:bg-warning/90',
  },
  failed: {
    label: 'Failed',
    icon: XCircle,
    variant: 'destructive',
    className: 'bg-destructive text-destructive-foreground',
  },
  pending: {
    label: 'Pending',
    icon: Clock,
    variant: 'outline',
    className: 'bg-muted text-muted-foreground',
  },
};

export function ClusterStatusBadge({ status, className }: ClusterStatusBadgeProps) {
  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <Badge 
      variant={config.variant}
      className={cn(config.className, 'gap-1.5 font-medium', className)}
    >
      <Icon className={cn('h-3 w-3', status === 'deploying' && 'animate-spin')} />
      {config.label}
    </Badge>
  );
}
