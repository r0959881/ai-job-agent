/* Who is signed in. Pages below <RequireUser> can rely on a user and their local database. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { SkeletonRows } from "@/components/states";
import { type SessionInfo, type SessionUser, SIGNED_OUT_EVENT, getSession, serverRequest } from "@/lib/api";
import { setLocalUser } from "@/lib/local/idb";
import { CHANGE_EVENT, syncProjectFiles } from "@/lib/local/store";

export const sessionKey = ["session"] as const;
const LOCAL_QUERIES = new Set(["jobs", "job", "documents", "stats", "runs", "document-preview"]);

export function useSession() {
  return useQuery({ queryKey: sessionKey, queryFn: () => getSession(true), staleTime: Infinity, retry: 1 });
}

export function useUser(): SessionUser {
  const { data } = useSession();
  if (!data?.user) throw new Error("useUser needs a signed-in user (wrap the page in RequireUser).");
  return data.user;
}

export function useSignOut() {
  const queryClient = useQueryClient();
  return React.useCallback(async () => {
    await serverRequest("POST", "/api/auth/logout").catch(() => undefined);
    setLocalUser(null);
    queryClient.clear();
    window.location.assign("/login");
  }, [queryClient]);
}

/** Refresh pages showing local data when it changes (a run adds jobs, another page saves a file). */
function useLocalChanges() {
  const queryClient = useQueryClient();
  React.useEffect(() => {
    let timer: number | undefined;
    const refresh = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(
        () =>
          queryClient.invalidateQueries({
            predicate: (query) => LOCAL_QUERIES.has(String(query.queryKey[0])),
          }),
        250,
      );
    };
    window.addEventListener(CHANGE_EVENT, refresh);
    return () => {
      window.removeEventListener(CHANGE_EVENT, refresh);
      window.clearTimeout(timer);
    };
  }, [queryClient]);
}

/** The local account shows the jobs and documents the project already has (jobs.db, output/). */
function ProjectFilesSync({ children }: { children: React.ReactNode }) {
  React.useEffect(() => {
    syncProjectFiles().catch((error) =>
      toast.error("Your existing jobs could not be loaded", { description: (error as Error).message }),
    );
  }, []);
  return <>{children}</>;
}

export function RequireUser({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const queryClient = useQueryClient();
  const location = useLocation();
  useLocalChanges();

  React.useEffect(() => {
    const signedOut = () =>
      queryClient.setQueryData<SessionInfo>(sessionKey, (current) =>
        current ? { ...current, user: null } : current,
      );
    window.addEventListener(SIGNED_OUT_EVENT, signedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, signedOut);
  }, [queryClient]);

  if (session.isPending) return <SkeletonRows className="p-8" rows={6} />;
  const user = session.data?.user;
  if (!user) {
    const next = `${location.pathname}${location.search}`;
    return (
      <Navigate to={`/login${next && next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`} replace />
    );
  }
  setLocalUser(user.id, session.data?.project_files);
  return <ProjectFilesSync>{children}</ProjectFilesSync>;
}
