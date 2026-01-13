// src/components/clusters/CreateClusterForm/vmSizes.ts
import { AZURE_VM_SIZES } from '@/types/clusterSize';

const ALLOWED_VM_SIZE_VALUES = new Set([
  'Standard_F8s',
  'Standard_D4s_v3',
  'Standard_D8s_v3',
  'Standard_D16s_v3',
]);

export function getAllowedVmSizes() {
  return AZURE_VM_SIZES.filter((s) => ALLOWED_VM_SIZE_VALUES.has(s.value));
}
