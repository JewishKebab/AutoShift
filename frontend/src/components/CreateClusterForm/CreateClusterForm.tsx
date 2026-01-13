// src/components/clusters/CreateClusterForm/CreateClusterForm.tsx
import { useMemo, useState } from 'react';
import { toast } from 'sonner';

import { useClusters } from '@/contexts/ClusterContext';
import { API_BASE, ensurePolicyExemption, createSubnets, pushInstallConfig } from '@/lib/api';

import { getAllowedVmSizes } from './vmSizes';
import type { SuggestResponse, SuggestedSubnets } from './types';
import { ClusterConfigurationCard } from './ClusterConfigurationCard';
import { InstallerLogsCard } from './InstallerLogsCard';
import { useInstallerLogs } from './useInstallerLogs';

export function CreateClusterForm() {
  const { refresh } = useClusters();

  const [name, setName] = useState('');
  const [masterNodeSize, setMasterNodeSize] = useState('Standard_D8s_v3');
  const [workerNodeSize, setWorkerNodeSize] = useState('Standard_D8s_v3');
  const [masterReplicas, setMasterReplicas] = useState(3);
  const [workerReplicas, setWorkerReplicas] = useState(3);

  const [isSearchingSubnets, setIsSearchingSubnets] = useState(false);
  const [subnetsFound, setSubnetsFound] = useState(false);
  const [suggestedSubnets, setSuggestedSubnets] = useState<SuggestedSubnets | null>(null);

  const [isCreating, setIsCreating] = useState(false);

  const vmSizes = getAllowedVmSizes();
  const logs = useInstallerLogs({ apiBase: API_BASE });

  //  Always create as "<name>-openshift" (but don't double-append)
  const finalClusterName = useMemo(() => {
    const trimmed = name.trim();
    if (!trimmed) return '';
    const lower = trimmed.toLowerCase();
    return lower.endsWith('-openshift') ? lower : `${lower}-openshift`;
  }, [name]);

  const onChangeName = (v: string) => {
    setName(v);
    setSubnetsFound(false);
    setSuggestedSubnets(null);
  };

  const handleFindSubnets = async () => {
    if (!finalClusterName) {
      toast.error('Please enter a cluster name first');
      return;
    }

    setIsSearchingSubnets(true);
    setSubnetsFound(false);
    setSuggestedSubnets(null);

    try {
      const res = await fetch(
        `${API_BASE}/api/subnets/suggest?clusterName=${encodeURIComponent(finalClusterName)}`,
        {
          method: 'GET',
          credentials: 'include',
          headers: { Accept: 'application/json' },
        }
      );

      const data = (await res.json()) as SuggestResponse;

      if (!res.ok || data.ok === false) {
        if (res.status === 409 && data.ok === false && data.conflicts?.length) {
          throw new Error(`Subnet name already exists: ${data.conflicts.join(', ')}`);
        }
        const missing =
          data.ok === false && data.missing?.length ? ` Missing: ${data.missing.join(', ')}` : '';
        const base = data.ok === false ? data.error : 'Failed to find subnets';
        throw new Error(base + missing);
      }

      setSuggestedSubnets({
        master: data.master,
        worker: data.worker,
        masterCidr: data.masterCidr,
        workerCidr: data.workerCidr,
      });
      setSubnetsFound(true);

      toast.success('Found suitable subnets!', { description: 'Available CIDR ranges found in VNet' });
    } catch (err: any) {
      const msg = err?.message || String(err);
      if (msg.includes('Missing cookie') || msg.includes('401')) {
        toast.error('You are not logged in', { description: 'Please sign in again and retry.' });
      } else if (msg.toLowerCase().includes('forbidden') || msg.includes('403')) {
        toast.error('Access denied', { description: 'Missing required "User" role.' });
      } else if (msg.toLowerCase().includes('subnet name already exists')) {
        toast.error('Name already used', { description: msg });
      } else {
        toast.error('Subnet search failed', { description: msg });
      }
    } finally {
      setIsSearchingSubnets(false);
    }
  };

  const handleCreateCluster = async () => {
    if (!finalClusterName) {
      toast.error('Please enter a cluster name');
      return;
    }
    if (!suggestedSubnets) {
      toast.error('Please find subnets first');
      return;
    }

    setIsCreating(true);

    try {
      // 1) Policy exemption
      const ex = await ensurePolicyExemption(finalClusterName);
      toast.success(ex.created ? 'Policy exemption created' : 'Policy exemption already exists', {
        description: ex.expiresOn ? `Expires: ${ex.expiresOn}` : undefined,
      });

      // 2) Create subnets
      await createSubnets({
        clusterName: finalClusterName,
        masterCidr: suggestedSubnets.masterCidr,
        workerCidr: suggestedSubnets.workerCidr,
      });
      toast.success('Subnets created');

      // 3) Push install-config.yaml (backend will ensure installer VM is up)
      await pushInstallConfig({
        clusterName: finalClusterName,
        masterCidr: suggestedSubnets.masterCidr,
        workerCidr: suggestedSubnets.workerCidr,
        masterVmSize: masterNodeSize,
        workerVmSize: workerNodeSize,
        masterReplicas,
        workerReplicas,
      });
      toast.success('install-config.yaml uploaded to installer VM');

      // 4) Start installer
      const startRes = await fetch(`${API_BASE}/api/installer/start`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ clusterName: finalClusterName }),
      });

      const startData = await startRes.json();
      if (!startRes.ok || !startData.ok) {
        throw new Error(startData?.error || 'Failed to start installer');
      }

      toast.success('Installer started', { description: `Job: ${startData.jobId}` });

      // 5) Attach logs immediately
      logs.actions.setPersistedCursor(0);
      await logs.actions.startLogStream(startData.jobId);

      // 6) Refresh Azure-discovered clusters (source of truth)
      await refresh();

      toast.success('Cluster creation initiated!', {
        description: `${finalClusterName} is now being deployed`,
      });

      // Reset form (keep logs visible)
      setName('');
      setSubnetsFound(false);
      setSuggestedSubnets(null);
    } catch (err: any) {
      const msg = err?.message || String(err);
      if (msg.includes('Missing cookie') || msg.includes('401')) {
        toast.error('You are not logged in', { description: 'Please sign in again.' });
      } else if (msg.includes('403') || msg.toLowerCase().includes('forbidden')) {
        toast.error('Access denied', { description: 'Missing required "User" role.' });
      } else {
        toast.error('Create cluster failed', { description: msg });
      }
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="font-display text-2xl font-bold tracking-tight">Create New Cluster</h2>
        <p className="text-muted-foreground mt-1">Configure and deploy a new OpenShift cluster on Azure</p>
      </div>

      <ClusterConfigurationCard
        name={name}
        setName={onChangeName}
        resolvedName={finalClusterName}
        vmSizes={vmSizes}
        masterNodeSize={masterNodeSize}
        setMasterNodeSize={setMasterNodeSize}
        workerNodeSize={workerNodeSize}
        setWorkerNodeSize={setWorkerNodeSize}
        masterReplicas={masterReplicas}
        setMasterReplicas={setMasterReplicas}
        workerReplicas={workerReplicas}
        setWorkerReplicas={setWorkerReplicas}
        isSearchingSubnets={isSearchingSubnets}
        subnetsFound={subnetsFound}
        suggestedSubnets={suggestedSubnets}
        onFindSubnets={handleFindSubnets}
        isCreating={isCreating}
        onCreateCluster={handleCreateCluster}
      />

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
          onClear={() => {
            logs.actions.setInstallLogs([]);
          }}
          logBoxRef={logs.ui.logBoxRef}
          isUserAtBottom={logs.ui.isUserAtBottom}
          scrollToBottom={logs.ui.scrollToBottom}
        />
      )}
    </div>
  );
}
