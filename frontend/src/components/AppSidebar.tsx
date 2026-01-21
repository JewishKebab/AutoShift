  import { PlusCircle, Trash2, LayoutDashboard, LogOut, Server } from 'lucide-react';
  import { NavLink as RouterNavLink, useLocation } from 'react-router-dom';
  import { cn } from '@/lib/utils';
  import { useAuth } from '@/contexts/AuthContext';
  import { useClusters } from '@/contexts/ClusterContext';
  import { Button } from '@/components/ui/button';
  import { ClusterStatusBadge } from './ClusterDiscovery/ClusterStatusBadge';
  import { ScrollArea } from '@/components/ui/scroll-area';

  const navigation = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'Create Cluster', href: '/dashboard/create', icon: PlusCircle },
    { name: 'Delete Cluster', href: '/dashboard/delete', icon: Trash2 },
  ];

  export function AppSidebar() {
    const location = useLocation();
    const { user, logout } = useAuth();

    // Backwards-compatible: supports old `clusters` and new `azureClusters`
    const clusterCtx = useClusters() as any;
    const clusters = (clusterCtx.azureClusters ?? clusterCtx.clusters ?? []) as Array<{
      id: string;
      name: string;
      status: string;
    }>;

    return (
<div className="fixed flex h-screen w-64 flex-col bg-sidebar border-r border-sidebar-border">
        {/* Logo */}
        <div className="flex h-16 items-center gap-2 px-4 border-b border-sidebar-border">
          <div className=" gradient-openshift-background ml-5 h-10 w-10 rounded-lg overflow-hidden flex items-center justify-center">
            <img src="/autoshiftlogo.png" alt="AutoShift logo" className="h-full w-full object-contain" />
          </div>
          <span className="mr-5 font-display font-bold text-lg tracking-tight">AutoShift </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <RouterNavLink
                key={item.name}
                to={item.href}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-sidebar-primary text-sidebar-primary-foreground'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                )}
              >
                <item.icon className="h-5 w-5" />
                {item.name}
              </RouterNavLink>
            );
          })}
        </nav>

        {/* Cluster Status Section */}
        <div className="border-t border-sidebar-border">
          <div className="p-4">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
              <Server className="h-3.5 w-3.5" />
              Clusters
            </h3>

            <ScrollArea className="h-40">
              <div className="space-y-2 pr-2">
                {clusters.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No clusters</p>
                ) : (
                  clusters.map((cluster) => (
                    <div
                      key={cluster.id}
                      className="flex items-center justify-between py-1.5 px-2 rounded-md bg-sidebar-accent/50"
                    >
                      <span className="text-xs font-medium truncate max-w-[140px]">
                        {/* Keep your original behavior but don’t break on weird names */}
                        {cluster.name?.split('-')[1] || cluster.name}
                      </span>
                      <ClusterStatusBadge status={cluster.status} className="text-[10px] px-1.5 py-0.5" />
                    </div>
                  ))
                )}
              </div>
            </ScrollArea>
          </div>
        </div>

        {/* User Section */}
        <div className="mt-auto border-t border-sidebar-border p-4 ">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
              <span className="text-sm font-semibold text-primary">{user?.name?.charAt(0)?.toUpperCase() ?? '?'}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.name}</p>
              <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={logout}
              className="text-muted-foreground hover:text-foreground"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    );
  }
