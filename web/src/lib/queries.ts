import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { IntegrationsStatus, Run, RunStep, SearchCatalog } from "@/lib/types";

export const keys = {
  resume: ["resume"] as const,
  resumeRaw: ["resume", "raw"] as const,
  backups: ["resume", "backups"] as const,
  settings: ["settings", "search"] as const,
  catalog: ["search", "catalog"] as const,
  secrets: ["settings", "secrets"] as const,
  integrations: ["integrations"] as const,
  runs: ["runs"] as const,
  run: (id: number) => ["runs", id] as const,
  jobs: (params: string) => ["jobs", params] as const,
  job: (id: string) => ["job", id] as const,
  documents: (params: string) => ["documents", params] as const,
  stats: ["stats"] as const,
};

export interface RunsList {
  items: Run[];
  active_id: number | null;
  active?: (Run & { steps: RunStep[] }) | null;
}

/** Polls the local run list lightly so the top bar knows when a run is active. */
export function useRunsList(limit = 50) {
  return useQuery({
    queryKey: [...keys.runs, limit],
    queryFn: () => api.get<RunsList>(`/api/runs?limit=${limit}`),
    refetchInterval: (query) => (query.state.data?.active_id ? 2000 : 15000),
  });
}

export function useIntegrations() {
  return useQuery({
    queryKey: keys.integrations,
    queryFn: () => api.get<IntegrationsStatus>("/api/integrations/status"),
    staleTime: 30_000,
  });
}

export function useSearchCatalog(enabled = true) {
  return useQuery({
    queryKey: keys.catalog,
    queryFn: () => api.get<SearchCatalog>("/api/search/catalog"),
    enabled,
    staleTime: 30_000,
  });
}
