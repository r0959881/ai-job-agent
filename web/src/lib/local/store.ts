/*
 * Jobs, documents and runs on the user's own device.
 *
 * Records live in IndexedDB (one database per user). Files go into the folder the
 * user picked, or into browser storage when no folder is connected. A copy of the
 * records is kept in the folder as ai-job-agent-data.json, so the data survives a
 * cleared browser and can be opened in another one.
 */
import { reduceSteps } from "@/features/runs/runSteps";
import * as folder from "@/lib/local/folder";
import * as idb from "@/lib/local/idb";
import * as project from "@/lib/local/projectFiles";
import type {
  ApplicationStatus,
  DocumentItem,
  DocumentKind,
  Job,
  JobDetail,
  JobsPage,
  Run,
  RunEvent,
  RunOptions,
  RunStep,
} from "@/lib/types";

export const CHANGE_EVENT = "local-data-changed";
export const APPLICATION_STATUSES: ApplicationStatus[] = [
  "not_applied",
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "skipped",
];
const CHECKLIST_KEYS = ["review", "cv", "cover_letter", "answers", "apply", "track"];
const APPLIED_STATES = ["applied", "interviewing", "offer", "rejected"];

export interface LocalDocument {
  id?: number;
  job_id: string | null;
  kind: DocumentKind;
  role_family: string;
  path: string;
  name: string;
  created_at: string;
  run_id: number | null;
  size: number;
  /** "server": the project's output/ folder (the local account on your own PC). */
  storage: "folder" | "browser" | "server";
}

export interface LocalRun extends Omit<Run, "steps" | "documents" | "duration_seconds"> {
  events: RunEvent[];
}

export class NotFound extends Error {}

const now = () => new Date().toISOString();

let mirrorTimer: number | undefined;

/** Tell open pages to refresh, and update the data file in the folder a moment later. */
export function changed() {
  window.dispatchEvent(new Event(CHANGE_EVENT));
  window.clearTimeout(mirrorTimer);
  mirrorTimer = window.setTimeout(() => {
    writeDataFile().catch(() => undefined);
  }, 1500);
}

// ------------------------------------------------------------------------------------ jobs

type StoredJob = Omit<Job, "has_cv">;

function blankJob(row: Partial<StoredJob> & { id: string }): StoredJob {
  return {
    title: "",
    company: "",
    location: "",
    url: "",
    source: "",
    status: "new",
    description: "",
    category: "",
    contract_type: "",
    salary_min: null,
    salary_max: null,
    salary_currency: "",
    posted_at: "",
    discovered_at: now(),
    cv_path: "",
    cover_letter_path: "",
    role_family: "",
    application_status: "not_applied",
    applied_at: "",
    notes: "",
    follow_up_at: "",
    apply_checklist: {},
    ...row,
  };
}

function withCv(job: StoredJob): Job {
  return { ...job, has_cv: Boolean(job.cv_path) };
}

export async function allJobs(): Promise<StoredJob[]> {
  return idb.getAll<StoredJob>("jobs");
}

async function jobOr404(id: string): Promise<StoredJob> {
  const job = await idb.get<StoredJob>("jobs", id);
  if (!job) throw new NotFound("That job no longer exists. It may have been deleted.");
  return job;
}

/** Merge jobs from a search. Returns how many were new and how many were already known. */
export async function upsertJobs(rows: (Partial<StoredJob> & { id: string })[], runId: number | null = null) {
  const existing = new Map((await allJobs()).map((job) => [job.id, job]));
  const seen = { last_seen_at: now(), last_run_id: runId };
  const updates: StoredJob[] = [];
  let added = 0;
  let known = 0;
  for (const row of rows) {
    const current = existing.get(row.id);
    if (!current) {
      const job = blankJob({ ...row, ...seen });
      existing.set(job.id, job);
      updates.push(job);
      added += 1;
      continue;
    }
    known += 1;
    const sources = current.source
      .split("|")
      .map((part) => part.trim())
      .filter(Boolean);
    if (row.source && !sources.includes(row.source)) sources.push(row.source);
    const merged: StoredJob = {
      ...current,
      source: sources.join(" | "),
      description: current.description || row.description || "",
      location: current.location || row.location || "",
      url: current.url || row.url || "",
      role_family: current.role_family || row.role_family || "",
      posted_at: current.posted_at || row.posted_at || "",
      ...seen,
    };
    existing.set(merged.id, merged);
    updates.push(merged);
  }
  await idb.putMany("jobs", updates);
  if (updates.length) changed();
  return { added, known };
}

const posted = (job: StoredJob) => job.posted_at || job.discovered_at || "";
const salary = (job: StoredJob) => job.salary_max ?? job.salary_min ?? -Infinity;

const SORTS: Record<string, (job: StoredJob) => string | number> = {
  title: (job) => job.title.toLowerCase(),
  company: (job) => job.company.toLowerCase(),
  location: (job) => job.location.toLowerCase(),
  role_family: (job) => job.role_family,
  source: (job) => job.source,
  posted,
  discovered: (job) => job.discovered_at,
  status: (job) => job.status,
  application_status: (job) => job.application_status,
  has_cv: (job) => (job.cv_path ? 1 : 0),
  salary,
};

/** The "Added" filter as the earliest discovered_at to keep, or null for any time. */
function addedCutoff(added: string | null): string | null {
  const hours: Record<string, number> = { "1h": 1, "24h": 24, "7d": 24 * 7 };
  return added && hours[added] ? new Date(Date.now() - hours[added] * 3600_000).toISOString() : null;
}

/** Whether a run returned the job: recorded since runs track it, else added while that run ran (older runs). */
function foundByRun(job: StoredJob, run: LocalRun | undefined) {
  if (!run) return false;
  if (job.last_run_id === run.id) return true;
  const end = run.finished_at || new Date().toISOString();
  return Boolean(job.discovered_at) && job.discovered_at >= run.started_at && job.discovered_at <= end;
}

/** The Jobs grid: the same filters, sorting and paging as the old /api/jobs. */
export async function listJobs(params: URLSearchParams): Promise<JobsPage> {
  const jobs = await allJobs();
  const q = (params.get("q") ?? "").toLowerCase();
  const list = (key: string) => params.getAll(key).filter(Boolean);
  const statuses = list("status");
  const applications = list("application_status");
  const families = list("role_family");
  const sources = list("source").map((source) => source.toLowerCase());
  const dateFrom = params.get("date_from") ?? "";
  const dateTo = params.get("date_to") ?? "";
  const hasCv = params.get("has_cv");
  const quick = params.get("quick");
  const weekAgo = new Date(Date.now() - 7 * 86400_000).toISOString();
  const added = params.get("added");
  const latestRun =
    added === "run" ? (await idb.getAll<LocalRun>("runs")).sort((a, b) => b.id - a.id)[0] : undefined;
  const addedSince = added === "run" ? null : addedCutoff(added);
  const endOfToday = `${new Date().toISOString().slice(0, 10)}T23:59:59`;

  const filtered = jobs.filter((job) => {
    if (
      q &&
      ![job.title, job.company, job.location, job.description].some((text) => text.toLowerCase().includes(q))
    )
      return false;
    if (statuses.length && !statuses.includes(job.status)) return false;
    if (applications.length && !applications.includes(job.application_status)) return false;
    if (families.length && !families.includes(job.role_family)) return false;
    if (sources.length && !sources.some((source) => job.source.toLowerCase().includes(source))) return false;
    if (dateFrom && posted(job) < dateFrom) return false;
    if (dateTo && posted(job) > (dateTo.length === 10 ? `${dateTo}T23:59:59.999` : dateTo)) return false;
    if (hasCv === "true" && !job.cv_path) return false;
    if (hasCv === "false" && job.cv_path) return false;
    if (quick === "ready" && !(job.cv_path && job.application_status === "not_applied")) return false;
    if (quick === "applied_week" && !(job.applied_at && job.applied_at >= weekAgo)) return false;
    if (quick === "follow_up" && !(job.follow_up_at && job.follow_up_at <= endOfToday)) return false;
    if (addedSince !== null && !(job.discovered_at && job.discovered_at >= addedSince)) return false;
    if (added === "run" && !foundByRun(job, latestRun)) return false;
    return true;
  });

  const key = SORTS[params.get("sort") ?? "posted"] ?? SORTS.posted;
  const direction = params.get("order") === "asc" ? 1 : -1;
  filtered.sort((a, b) => {
    const left = key(a);
    const right = key(b);
    if (left < right) return -direction;
    if (left > right) return direction;
    return a.id < b.id ? -1 : 1;
  });
  const page = Math.max(1, Number(params.get("page") ?? 1) || 1);
  const size = Math.max(1, Math.min(Number(params.get("page_size") ?? 50) || 50, 500));
  return {
    items: filtered.slice((page - 1) * size, page * size).map(withCv),
    total: filtered.length,
    page,
    page_size: size,
    facets: {
      sources: [
        ...new Set(jobs.flatMap((job) => job.source.split("|").map((s) => s.trim())).filter(Boolean)),
      ].sort(),
      role_families: [...new Set(jobs.map((job) => job.role_family).filter(Boolean))].sort(),
    },
  };
}

export async function jobDetail(
  id: string,
): Promise<Omit<JobDetail, "matched_keywords" | "missing_keywords" | "tips">> {
  const job = await jobOr404(id);
  const documents = await documentsFor({ job_id: id });
  const history = [{ at: job.discovered_at, text: `Found via ${job.source || "unknown source"}` }];
  for (const doc of documents) {
    if (doc.kind === "cv" || doc.kind === "cover_letter")
      history.push({ at: doc.created_at, text: `${doc.kind === "cv" ? "CV" : "Cover letter"} generated` });
  }
  if (job.applied_at) history.push({ at: job.applied_at, text: "Marked as applied" });
  return {
    ...withCv(job),
    documents,
    history: history.filter((item) => item.at).sort((a, b) => (a.at < b.at ? 1 : -1)),
  };
}

export async function updateJob(id: string, changes: Partial<Job>) {
  const job = await jobOr404(id);
  const next: StoredJob = { ...job };
  if (changes.application_status !== undefined) {
    if (!APPLICATION_STATUSES.includes(changes.application_status))
      throw new Error(`Unknown application status “${changes.application_status}”.`);
    next.application_status = changes.application_status;
    if (APPLIED_STATES.includes(changes.application_status) && !changes.applied_at && !job.applied_at) {
      if (changes.application_status !== "rejected") next.applied_at = now();
    }
  }
  for (const key of ["applied_at", "follow_up_at", "notes"] as const) {
    if (changes[key] !== undefined && changes[key] !== null) next[key] = changes[key] as string;
  }
  if (changes.apply_checklist) {
    next.apply_checklist = Object.fromEntries(
      Object.entries(changes.apply_checklist)
        .filter(([key]) => CHECKLIST_KEYS.includes(key))
        .map(([key, value]) => [key, Boolean(value)]),
    );
  }
  if (changes.status && ["new", "processed", "rejected"].includes(changes.status))
    next.status = changes.status;
  if (changes.cv_path !== undefined) next.cv_path = changes.cv_path;
  if (changes.cover_letter_path !== undefined) next.cover_letter_path = changes.cover_letter_path;
  if (changes.role_family !== undefined) next.role_family = changes.role_family;
  await idb.put("jobs", next);
  changed();
  return next;
}

export async function deleteJob(id: string, deleteFiles = false) {
  await jobOr404(id);
  const removed: string[] = [];
  for (const doc of await documentsFor({ job_id: id })) {
    if (deleteFiles) {
      await deleteDocument(doc.id, false);
      removed.push(doc.path);
    } else {
      await idb.put("documents", { ...(await idb.get<LocalDocument>("documents", doc.id)), job_id: null });
    }
  }
  await idb.remove("jobs", id);
  changed();
  return { deleted: id, files_removed: removed };
}

export async function resetJobs() {
  const jobs = await allJobs();
  for (const doc of await idb.getAll<LocalDocument>("documents")) {
    if (doc.job_id) await idb.put("documents", { ...doc, job_id: null });
  }
  await idb.clear("jobs");
  changed();
  return { deleted: jobs.length };
}

// ------------------------------------------------------------------------------- documents

function toItem(doc: LocalDocument, jobs: Map<string, StoredJob>): DocumentItem {
  const job = doc.job_id ? jobs.get(doc.job_id) : undefined;
  return {
    id: doc.id as number,
    job_id: doc.job_id,
    kind: doc.kind,
    role_family: doc.role_family,
    path: doc.path,
    name: doc.name,
    created_at: doc.created_at,
    run_id: doc.run_id,
    size: doc.size,
    exists: true,
    job_title: job?.title ?? null,
    job_company: job?.company ?? null,
  };
}

export async function documentsFor(filters: {
  kind?: string | null;
  role_family?: string | null;
  q?: string | null;
  job_id?: string | null;
  orphans?: boolean;
  run_id?: number;
}): Promise<DocumentItem[]> {
  const jobs = new Map((await allJobs()).map((job) => [job.id, job]));
  const q = (filters.q ?? "").toLowerCase();
  return (await idb.getAll<LocalDocument>("documents"))
    .filter((doc) => !filters.kind || doc.kind === filters.kind)
    .filter((doc) => !filters.role_family || doc.role_family === filters.role_family)
    .filter((doc) => !filters.job_id || doc.job_id === filters.job_id)
    .filter((doc) => filters.run_id === undefined || doc.run_id === filters.run_id)
    .filter((doc) => !filters.orphans || ((!doc.job_id || !jobs.has(doc.job_id)) && doc.kind !== "report"))
    .filter((doc) => {
      if (!q) return true;
      const job = doc.job_id ? jobs.get(doc.job_id) : undefined;
      return [doc.path, job?.title ?? "", job?.company ?? ""].some((text) => text.toLowerCase().includes(q));
    })
    .sort((a, b) =>
      a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : (b.id ?? 0) - (a.id ?? 0),
    )
    .map((doc) => toItem(doc, jobs));
}

function safeName(name: string) {
  return (
    name
      .replace(/[\\/:*?"<>|]+/g, "_")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 180) || "document"
  );
}

/** Save a generated file in the folder (or browser storage) and record it. Same path = replaced. */
export async function saveDocument(input: {
  kind: DocumentKind;
  name: string;
  blob: Blob;
  job_id?: string | null;
  role_family?: string;
  run_id?: number | null;
}): Promise<DocumentItem> {
  const name = safeName(input.name);
  const onServer = idb.projectFiles();
  const path = onServer ? `${project.OUTPUT}/${name}` : `${folder.FOLDERS[input.kind]}/${name}`;
  const root = onServer ? null : await folder.readyFolder();
  if (onServer) await project.writeFile(name, input.blob);
  else if (root) await folder.writeFile(root, path, input.blob);
  const [previous] = await idb.getByIndex<LocalDocument>("documents", "path", path);
  const doc: LocalDocument = {
    ...(previous?.id ? { id: previous.id } : {}),
    job_id: input.job_id ?? previous?.job_id ?? null,
    kind: input.kind,
    role_family: input.role_family ?? "",
    path,
    name,
    created_at: now(),
    run_id: input.run_id ?? null,
    size: input.blob.size,
    storage: onServer ? "server" : root ? "folder" : "browser",
  };
  const id = (await idb.put("documents", doc)) as number;
  if (root || onServer) await idb.remove("blobs", id);
  else await idb.put("blobs", { id, blob: input.blob });
  changed();
  return toItem({ ...doc, id }, new Map((await allJobs()).map((job) => [job.id, job])));
}

/** The file of a document, from the folder or browser storage (null when it was deleted). */
export async function documentFile(id: number): Promise<File | null> {
  const doc = await idb.get<LocalDocument>("documents", id);
  if (!doc) throw new NotFound("That document no longer exists.");
  if (doc.storage === "browser") {
    const stored = await idb.get<{ id: number; blob: Blob }>("blobs", id);
    return stored ? new File([stored.blob], doc.name) : null;
  }
  if (doc.storage === "server") return project.readFile(doc.name);
  const root = await folder.readyFolder();
  if (!root) throw new Error("Reconnect your documents folder (Settings → Storage) to open this file.");
  return folder.readFile(root, doc.path);
}

export async function deleteDocument(id: number, notify = true) {
  const doc = await idb.get<LocalDocument>("documents", id);
  if (!doc) throw new NotFound("That document no longer exists.");
  if (doc.storage === "folder") {
    const root = await folder.readyFolder();
    if (root) await folder.removeFile(root, doc.path);
  } else if (doc.storage === "server") {
    await project.removeFile(doc.name);
  }
  await idb.remove("blobs", id);
  await idb.remove("documents", id);
  if (doc.job_id) {
    const job = await idb.get<StoredJob>("jobs", doc.job_id);
    if (job && (job.cv_path === doc.path || job.cover_letter_path === doc.path)) {
      await idb.put("jobs", {
        ...job,
        cv_path: job.cv_path === doc.path ? "" : job.cv_path,
        cover_letter_path: job.cover_letter_path === doc.path ? "" : job.cover_letter_path,
        status: job.cv_path === doc.path && job.status === "processed" ? "new" : job.status,
      });
    }
  }
  if (notify) changed();
  return { deleted: id };
}

/** Match the records to the files in the folder: add files found there, drop records whose file is gone. */
export async function rescanFolder() {
  if (idb.projectFiles()) return rescanProjectFiles();
  const root = await folder.readyFolder();
  const counts = { added: 0, removed: 0, linked: 0 };
  if (!root) return counts;
  const docs = await idb.getAll<LocalDocument>("documents");
  const byPath = new Map(docs.filter((doc) => doc.storage === "folder").map((doc) => [doc.path, doc]));
  const jobs = await allJobs();
  const jobByCv = new Map(
    jobs.flatMap(
      (job) =>
        [
          [job.cv_path, job.id],
          [job.cover_letter_path, job.id],
        ] as const,
    ),
  );
  const seen = new Set<string>();
  for (const [kind, name] of Object.entries(folder.FOLDERS) as [DocumentKind, string][]) {
    for (const { path, file } of await folder.listFiles(root, name)) {
      seen.add(path);
      if (byPath.has(path)) continue;
      const jobId = jobByCv.get(path) ?? null;
      await idb.put("documents", {
        job_id: jobId,
        kind,
        role_family: "",
        path,
        name: file.name,
        created_at: new Date(file.lastModified).toISOString(),
        run_id: null,
        size: file.size,
        storage: "folder",
      } satisfies LocalDocument);
      counts.added += 1;
      if (jobId) counts.linked += 1;
    }
  }
  for (const [path, doc] of byPath) {
    if (!seen.has(path) && doc.id) {
      await idb.remove("documents", doc.id);
      counts.removed += 1;
    }
  }
  changed();
  return counts;
}

/** Copy documents kept in browser storage into the folder (after the user connects one). */
export async function moveBrowserFilesToFolder() {
  const root = await folder.readyFolder();
  if (!root) return 0;
  let moved = 0;
  for (const doc of await idb.getAll<LocalDocument>("documents")) {
    if (doc.storage !== "browser" || !doc.id) continue;
    const stored = await idb.get<{ id: number; blob: Blob }>("blobs", doc.id);
    if (stored) await folder.writeFile(root, doc.path, stored.blob);
    await idb.put("documents", { ...doc, storage: "folder" });
    await idb.remove("blobs", doc.id);
    moved += 1;
  }
  if (moved) changed();
  return moved;
}

// ------------------------------------------------------------------------------------ runs

export async function createRun(options: Partial<RunOptions>): Promise<number> {
  const run: Omit<LocalRun, "id"> = {
    started_at: now(),
    finished_at: "",
    status: "running",
    discovered: 0,
    new: 0,
    filtered: 0,
    tailored: 0,
    failed: 0,
    error: "",
    log_path: "",
    options,
    summary: {},
    events: [],
  };
  const id = (await idb.put("runs", run)) as number;
  changed();
  return id;
}

export async function getRunRecord(id: number) {
  const run = await idb.get<LocalRun>("runs", id);
  if (!run) throw new NotFound(`Run ${id} does not exist.`);
  return run;
}

export async function saveRun(run: LocalRun) {
  await idb.put("runs", run);
  changed();
}

function toRun(run: LocalRun, withSteps: boolean): Run & { steps?: RunStep[] } {
  const { events, ...rest } = run;
  const duration =
    run.started_at && run.finished_at
      ? (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000
      : null;
  return { ...rest, duration_seconds: duration, ...(withSteps ? { steps: reduceSteps(events) } : {}) };
}

/** Runs marked "running" that no tab is driving (the page was closed) are marked failed. */
export async function settleOrphanRuns(activeId: number | null) {
  for (const run of await idb.getAll<LocalRun>("runs")) {
    if (run.status === "running" && run.id !== activeId) {
      await idb.put("runs", {
        ...run,
        status: "failed",
        finished_at: run.finished_at || now(),
        error: "The page was closed or reloaded while this run was in progress.",
      });
    }
  }
}

export async function listRuns(limit: number, activeId: number | null) {
  const runs = (await idb.getAll<LocalRun>("runs")).sort((a, b) => b.id - a.id);
  const active = activeId != null ? runs.find((run) => run.id === activeId) : undefined;
  return {
    items: runs.slice(0, limit).map((run) => toRun(run, false)),
    active_id: active ? active.id : null,
    active: active ? toRun(active, true) : null,
  };
}

export async function runDetail(id: number) {
  const run = await getRunRecord(id);
  return { ...toRun(run, true), documents: await documentsFor({ run_id: id }) };
}

export async function runLog(id: number) {
  const run = await getRunRecord(id);
  return run.events
    .filter((event) => event.message && event.status !== "progress")
    .map(
      (event) =>
        `${event.ts} ${String(event.data?.level ?? event.status)
          .toUpperCase()
          .padEnd(9)} [${event.step ?? "-"}] ${event.message}`,
    )
    .join("\n");
}

// ----------------------------------------------------------------------------------- stats

export async function stats(windowHours: number) {
  const jobs = await allJobs();
  const docs = await idb.getAll<LocalDocument>("documents");
  const since = new Date(Date.now() - windowHours * 3600_000).toISOString();
  const applied = jobs.filter(
    (job) => APPLIED_STATES.includes(job.application_status) && job.applied_at,
  ).length;
  const interviewing = jobs.filter((job) =>
    ["interviewing", "offer"].includes(job.application_status),
  ).length;
  const tailored = jobs.filter((job) => job.cv_path).length;
  const runs = (await idb.getAll<LocalRun>("runs")).sort((a, b) => b.id - a.id);
  return {
    jobs_last_window: jobs.filter((job) => posted(job) >= since).length,
    window_hours: windowHours,
    cvs_generated: docs.filter((doc) => doc.kind === "cv").length,
    applications_sent: applied,
    interviews: interviewing,
    funnel: [
      { key: "discovered", label: "Discovered", count: jobs.length },
      { key: "eligible", label: "Eligible", count: jobs.filter((job) => job.status !== "rejected").length },
      { key: "tailored", label: "CV tailored", count: tailored },
      { key: "applied", label: "Applied", count: applied },
      { key: "interviewing", label: "Interviewing", count: interviewing },
    ],
    last_run: runs[0] ? toRun(runs[0], true) : null,
    ready_to_apply: jobs
      .filter((job) => job.cv_path && job.application_status === "not_applied")
      .sort((a, b) => (posted(a) < posted(b) ? 1 : -1))
      .slice(0, 8)
      .map(withCv),
  };
}

// ----------------------------------------------------------------------- folder data file

interface DataFile {
  app: "ai-job-agent";
  version: 1;
  saved_at: string;
  jobs: StoredJob[];
  documents: LocalDocument[];
  runs: LocalRun[];
}

export async function exportData(): Promise<DataFile> {
  return {
    app: "ai-job-agent",
    version: 1,
    saved_at: now(),
    jobs: await allJobs(),
    documents: (await idb.getAll<LocalDocument>("documents")).filter((doc) => doc.storage !== "browser"),
    runs: await idb.getAll<LocalRun>("runs"),
  };
}

export async function writeDataFile() {
  if (idb.projectFiles()) {
    await project.writeFile(folder.DATA_FILE, JSON.stringify(await exportData(), null, 1));
    return true;
  }
  const root = await folder.readyFolder();
  if (!root) return false;
  await folder.writeFile(root, folder.DATA_FILE, JSON.stringify(await exportData(), null, 1));
  return true;
}

/** Load ai-job-agent-data.json from a folder the user just connected (records already here win). */
export async function importDataFile() {
  const root = idb.projectFiles() ? null : await folder.readyFolder();
  if (!root && !idb.projectFiles()) return { jobs: 0, runs: 0 };
  const file = root
    ? await folder.readFile(root, folder.DATA_FILE)
    : await project.readFile(folder.DATA_FILE);
  if (!file) return { jobs: 0, runs: 0 };
  let data: DataFile;
  try {
    data = JSON.parse(await file.text()) as DataFile;
  } catch {
    return { jobs: 0, runs: 0 };
  }
  if (data?.app !== "ai-job-agent") return { jobs: 0, runs: 0 };
  const knownJobs = new Set((await allJobs()).map((job) => job.id));
  const jobs = (data.jobs ?? []).filter((job) => job?.id && !knownJobs.has(job.id));
  await idb.putMany("jobs", jobs);
  const knownRuns = new Set((await idb.getAll<LocalRun>("runs")).map((run) => run.started_at));
  const runs = (data.runs ?? []).filter((run) => run?.started_at && !knownRuns.has(run.started_at));
  for (const run of runs) {
    const { id: _old, ...rest } = run;
    await idb.put("runs", rest);
  }
  const knownPaths = new Set((await idb.getAll<LocalDocument>("documents")).map((doc) => doc.path));
  for (const doc of data.documents ?? []) {
    if (doc?.path && !knownPaths.has(doc.path)) {
      const { id: _old, ...rest } = doc;
      await idb.put("documents", { ...rest, storage: idb.projectFiles() ? "server" : "folder" });
    }
  }
  changed();
  return { jobs: jobs.length, runs: runs.length };
}

// ------------------------------------------------------------ the local account's project files

/** Match the records to the files in output/: add files found there, drop records whose file is gone. */
async function rescanProjectFiles() {
  const counts = { added: 0, removed: 0, linked: 0 };
  const files = await project.listFiles();
  const docs = (await idb.getAll<LocalDocument>("documents")).filter((doc) => doc.storage === "server");
  const known = new Set(docs.map((doc) => doc.path));
  const present = new Set(files.map((file) => file.path));
  const owner = new Map(
    (await allJobs()).flatMap(
      (job) =>
        [
          [job.cv_path, job.id],
          [job.cover_letter_path, job.id],
        ] as const,
    ),
  );
  for (const file of files) {
    if (known.has(file.path) || file.name === folder.DATA_FILE) continue;
    const jobId = owner.get(file.path) ?? null;
    await idb.put("documents", {
      job_id: jobId,
      kind: file.kind,
      role_family: "",
      path: file.path,
      name: file.name,
      created_at: file.modified,
      run_id: null,
      size: file.size,
      storage: "server",
    } satisfies LocalDocument);
    counts.added += 1;
    if (jobId) counts.linked += 1;
  }
  for (const doc of docs) {
    if (!present.has(doc.path) && doc.id) {
      await idb.remove("documents", doc.id);
      counts.removed += 1;
    }
  }
  changed();
  return counts;
}

let synced: number | null = null;

/**
 * Bring in what the project already has (local account only): the jobs in jobs.db with their
 * application tracking, the documents in output/, and jobs saved by earlier web runs.
 * Jobs already in this browser keep their newer state. Runs once per page load.
 */
export async function syncProjectFiles() {
  const user = idb.localUser();
  if (!idb.projectFiles() || user == null || synced === user) return null;
  synced = user;
  const { jobs, documents, runs } = await project.legacy();
  const known = new Set((await allJobs()).map((job) => job.id));
  const fresh = jobs.filter((job) => !known.has(job.id)).map((job) => blankJob(job));
  await idb.putMany("jobs", fresh);
  const knownPaths = new Set((await idb.getAll<LocalDocument>("documents")).map((doc) => doc.path));
  const docs = documents
    .filter((doc) => !knownPaths.has(doc.path))
    .map((doc) => ({ ...doc, run_id: null, storage: "server" }) satisfies LocalDocument);
  await idb.putMany("documents", docs);
  const knownRuns = new Set((await idb.getAll<LocalRun>("runs")).map((run) => run.started_at));
  for (const run of runs.filter((item) => item.started_at && !knownRuns.has(item.started_at))) {
    await idb.put("runs", run);
  }
  const restored = await importDataFile();
  if (fresh.length || docs.length) changed();
  return { jobs: fresh.length + restored.jobs, documents: docs.length };
}
