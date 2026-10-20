/*
 * The project's output/ folder, for the local account on your own PC (`start.ps1`).
 *
 * Instead of a folder picked in the browser, the local account reads and writes the
 * same output/ folder the command line uses, through the local server. It also brings
 * in the jobs and documents recorded in jobs.db.
 */
import { ApiError, serverRequest } from "@/lib/api";
import type { DocumentKind, Job, Run, RunEvent } from "@/lib/types";

export const OUTPUT = "output";

export interface LegacyDocument {
  job_id: string | null;
  kind: DocumentKind;
  role_family: string;
  path: string;
  name: string;
  created_at: string;
  size: number;
}

const url = (name: string) => `/api/local/files/${encodeURIComponent(name)}`;

export async function writeFile(name: string, data: Blob | string) {
  const blob = typeof data === "string" ? new Blob([data], { type: "application/json" }) : data;
  await serverRequest("PUT", url(name), blob);
  return `${OUTPUT}/${name}`;
}

export async function readFile(name: string): Promise<File | null> {
  const response = await fetch(url(name), { credentials: "same-origin" });
  if (response.status === 404) return null;
  if (!response.ok)
    throw new ApiError(response.status, `${name} could not be read from the output folder.`, null);
  return new File([await response.blob()], name);
}

export async function removeFile(name: string) {
  await serverRequest("DELETE", url(name));
}

export async function listFiles() {
  return (
    await serverRequest<{
      items: { name: string; path: string; size: number; modified: string; kind: DocumentKind }[];
    }>("GET", "/api/local/files")
  ).items;
}

export type LegacyRun = Omit<Run, "id" | "steps" | "documents" | "duration_seconds"> & { events: RunEvent[] };

export async function legacy() {
  return serverRequest<{
    jobs: (Omit<Job, "has_cv"> & { id: string })[];
    documents: LegacyDocument[];
    runs: LegacyRun[];
  }>("GET", "/api/local/legacy");
}
