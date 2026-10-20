/*
 * The job, document, run and stats endpoints, answered on this device.
 *
 * These used to be server endpoints. Jobs and files now stay with the user, so
 * lib/api.ts sends requests for these paths here instead of to the server. The
 * responses keep their old shapes, so pages did not have to change. Work that
 * needs the server (tailoring, letters, previews) is a call to its stateless API.
 */
import { ApiError, serverRequest } from "@/lib/api";
import * as runner from "@/lib/local/runner";
import * as store from "@/lib/local/store";
import type { DocumentItem, Job, RunOptions } from "@/lib/types";

type Handler = (match: RegExpMatchArray, body: unknown, params: URLSearchParams) => Promise<unknown>;

interface FilePayload {
  name: string;
  mime: string;
  size: number;
  data: string;
}

const routes: [string, RegExp, Handler][] = [];
const route = (method: string, pattern: RegExp, handler: Handler) => routes.push([method, pattern, handler]);

export function isLocal(path: string) {
  return (
    /^\/api\/(jobs|documents|runs|stats|data)(\/|\?|$)/.test(path) && !path.startsWith("/api/jobs/insights")
  );
}

export async function handleLocal(method: string, url: string, body: unknown) {
  const parsed = new URL(url, window.location.origin);
  for (const [verb, pattern, handler] of routes) {
    const match = parsed.pathname.match(pattern);
    if (verb === method && match) {
      try {
        return await handler(match, body, parsed.searchParams);
      } catch (error) {
        if (error instanceof ApiError) throw error;
        if (error instanceof store.NotFound) throw new ApiError(404, error.message, error.message);
        throw new ApiError(400, (error as Error).message, (error as Error).message);
      }
    }
  }
  throw new ApiError(404, `No API endpoint at ${parsed.pathname}.`, null);
}

/** Trigger a browser download of a file. */
export function downloadBlob(blob: Blob, name: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
}

export async function downloadDocument(id: number) {
  const file = await store.documentFile(id);
  if (!file) throw new Error("The file is no longer in your documents folder.");
  downloadBlob(file, file.name);
  return file.name;
}

const jobForServer = (job: Job) => ({
  id: job.id,
  title: job.title,
  company: job.company,
  location: job.location,
  url: job.url,
  source: job.source,
  description: job.description,
  role_family: job.role_family,
});

async function detailWithInsights(id: string) {
  const job = await store.jobDetail(id);
  try {
    const insights = await serverRequest<{
      matched_keywords: string[];
      missing_keywords: string[];
      tips: string[];
    }>("POST", "/api/jobs/insights", jobForServer(job));
    return { ...job, ...insights };
  } catch {
    return { ...job, matched_keywords: [], missing_keywords: [], tips: [] };
  }
}

async function tailorJob(
  id: string,
  edits: { summary?: string; bullets?: string[]; role_family?: string } = {},
) {
  const job = await store.jobDetail(id);
  const result = await serverRequest<{ role_family: string; file: FilePayload }>("POST", "/api/tailor", {
    job: jobForServer(job),
    ...edits,
  });
  const doc = await store.saveDocument({
    kind: "cv",
    name: result.file.name,
    blob: runner.payloadToBlob(result.file),
    job_id: id,
    role_family: result.role_family,
  });
  await store.updateJob(id, {
    cv_path: doc.path,
    status: "processed",
    role_family: result.role_family || job.role_family,
  });
  return { path: doc.path, job: await detailWithInsights(id) };
}

async function coverLetter(id: string, company?: string | null) {
  const job = await store.jobDetail(id);
  const result = await serverRequest<{ role_family: string; file: FilePayload }>(
    "POST",
    "/api/cover-letter",
    {
      job: jobForServer(job),
      company,
    },
  );
  const doc = await store.saveDocument({
    kind: "cover_letter",
    name: result.file.name,
    blob: runner.payloadToBlob(result.file),
    job_id: id,
    role_family: result.role_family,
  });
  await store.updateJob(id, { cover_letter_path: doc.path });
  return { path: doc.path, job: await detailWithInsights(id) };
}

// ------------------------------------------------------------------------------------ jobs

route("GET", /^\/api\/jobs$/, (_m, _b, params) => store.listJobs(params));
route("POST", /^\/api\/jobs\/bulk$/, async (_m, body) => {
  const { ids, action, delete_files } = body as { ids: string[]; action: string; delete_files?: boolean };
  const done: string[] = [];
  const failed: { id: string; reason: string }[] = [];
  for (const id of ids.slice(0, 500)) {
    try {
      if (action === "skip") await store.updateJob(id, { application_status: "skipped" });
      else if (action === "regenerate") await tailorJob(id);
      else await store.deleteJob(id, Boolean(delete_files));
      done.push(id);
    } catch (error) {
      failed.push({ id, reason: (error as Error).message });
    }
  }
  return { done, failed };
});
route("GET", /^\/api\/jobs\/([^/]+)$/, (m) => detailWithInsights(decodeURIComponent(m[1])));
route("PATCH", /^\/api\/jobs\/([^/]+)$/, async (m, body) => {
  await store.updateJob(decodeURIComponent(m[1]), body as Partial<Job>);
  return detailWithInsights(decodeURIComponent(m[1]));
});
route("DELETE", /^\/api\/jobs\/([^/]+)$/, (m, _b, params) =>
  store.deleteJob(decodeURIComponent(m[1]), params.get("delete_files") === "true"),
);
route("POST", /^\/api\/jobs\/([^/]+)\/tailor\/preview$/, async (m) => {
  const job = await store.jobDetail(decodeURIComponent(m[1]));
  return serverRequest("POST", "/api/tailor/preview", { job: jobForServer(job) });
});
route("POST", /^\/api\/jobs\/([^/]+)\/tailor$/, (m, body) =>
  tailorJob(
    decodeURIComponent(m[1]),
    (body ?? {}) as { summary?: string; bullets?: string[]; role_family?: string },
  ),
);
route("POST", /^\/api\/jobs\/([^/]+)\/cover-letter$/, (m, body) =>
  coverLetter(decodeURIComponent(m[1]), (body as { company?: string | null } | undefined)?.company),
);

// ------------------------------------------------------------------------------- documents

route("GET", /^\/api\/documents$/, async (_m, _b, params) => {
  if (params.get("rescan") === "true") await store.rescanFolder();
  return {
    items: await store.documentsFor({
      kind: params.get("kind"),
      role_family: params.get("role_family"),
      q: params.get("q"),
      job_id: params.get("job_id"),
      orphans: params.get("orphans") === "true",
    }),
  };
});
route("POST", /^\/api\/documents\/rescan$/, () => store.rescanFolder());
route("POST", /^\/api\/documents\/bulk-delete$/, async (_m, body) => {
  const deleted: number[] = [];
  const failed: { id: number; reason: string }[] = [];
  for (const id of (body as { ids: number[] }).ids) {
    try {
      await store.deleteDocument(id, false);
      deleted.push(id);
    } catch (error) {
      failed.push({ id, reason: (error as Error).message });
    }
  }
  store.changed();
  return { deleted, failed };
});
route("GET", /^\/api\/documents\/(\d+)\/preview$/, async (m) => {
  const file = await store.documentFile(Number(m[1]));
  if (!file) throw new ApiError(404, "The file is no longer in your documents folder.", null);
  const form = new FormData();
  form.append("file", file, file.name);
  return serverRequest("POST", "/api/documents/preview", form);
});
route("POST", /^\/api\/documents\/(\d+)\/open$/, async (m) => ({
  opened: await downloadDocument(Number(m[1])),
}));
route("POST", /^\/api\/documents\/(\d+)\/regenerate$/, async (m) => {
  const all = await store.documentsFor({});
  const doc = all.find((item: DocumentItem) => item.id === Number(m[1]));
  if (!doc) throw new store.NotFound("That document no longer exists.");
  if (!doc.job_id) throw new ApiError(400, "Only documents that belong to a job can be regenerated.", null);
  return doc.kind === "cover_letter" ? coverLetter(doc.job_id) : tailorJob(doc.job_id);
});
route("DELETE", /^\/api\/documents\/(\d+)$/, (m) => store.deleteDocument(Number(m[1])));

// ------------------------------------------------------------------------------------ runs

route("GET", /^\/api\/runs$/, async (_m, _b, params) => {
  const activeId = runner.activeRunId();
  await store.settleOrphanRuns(activeId);
  return store.listRuns(Number(params.get("limit") ?? 50) || 50, activeId);
});
route("POST", /^\/api\/runs$/, async (_m, body) => ({
  id: await runner.startRun((body ?? {}) as Partial<RunOptions>),
}));
route("GET", /^\/api\/runs\/(\d+)$/, (m) => store.runDetail(Number(m[1])));
route("GET", /^\/api\/runs\/(\d+)\/log$/, (m) => store.runLog(Number(m[1])));
route("POST", /^\/api\/runs\/(\d+)\/cancel$/, async (m) => {
  if (!runner.cancelRun(Number(m[1])))
    throw new ApiError(409, "This run is not running, so there is nothing to cancel.", null);
  return { cancelling: true };
});

// ----------------------------------------------------------------------------- stats, data

route("GET", /^\/api\/stats$/, async () => {
  const [settings, integrations] = await Promise.all([
    serverRequest<{ settings: { time_window_hours: number } }>("GET", "/api/settings/search").catch(
      () => null,
    ),
    serverRequest("GET", "/api/integrations/status").catch(() => ({})),
  ]);
  return { ...(await store.stats(settings?.settings.time_window_hours ?? 48)), integrations };
});
route("POST", /^\/api\/data\/reset-jobs$/, async (_m, body) => {
  if ((body as { confirm?: string })?.confirm !== "RESET")
    throw new ApiError(400, "Type RESET to confirm.", null);
  return store.resetJobs();
});
