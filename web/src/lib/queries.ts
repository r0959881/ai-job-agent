import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { GmailStatus, IntegrationsStatus, Run, RunStep } from "@/lib/types";

export const keys = {
  resume: ["resume"] as const,
  resumeRaw: ["resume", "raw"] as const,
  backups: ["resume", "backups"] as const,
  settings: ["settings", "search"] as const,
  secrets: ["settings", "secrets"] as const,
  integrations: ["integrations"] as const,
  gmail: ["integrations", "gmail"] as const,
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

/** Polls lightly so the top bar knows when a run is active (SSE takes over on the run page). */
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

export function useGmailStatus() {
  return useQuery({
    queryKey: keys.gmail,
    queryFn: () => api.get<GmailStatus>("/api/integrations/gmail/status"),
    staleTime: 30_000,
  });
}
