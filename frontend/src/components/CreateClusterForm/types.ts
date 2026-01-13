// src/components/clusters/CreateClusterForm/types.ts

export type SuggestedSubnets = {
  master: string;
  worker: string;
  masterCidr: string;
  workerCidr: string;
};

export type SuggestOk = {
  ok: true;
  vnet: string;
  master: string;
  worker: string;
  masterCidr: string;
  workerCidr: string;
};

export type SuggestErr = {
  ok: false;
  error: string;
  missing?: string[];
  conflicts?: string[];
};

export type SuggestResponse = SuggestOk | SuggestErr;
