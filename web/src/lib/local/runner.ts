/*
 * The agent run, driven from this browser tab.
 *
 * The server does one bounded piece of work per request (one search, one CV), so a
 * run never hits a shared host's request timeout. Jobs and files stay on this
 * device. The events have the same shape the old server stream had, so the run
 * page, stepper and log work unchanged. Closing the tab stops the run.
 */
import { ApiError, api } from "@/lib/api";
import * as store from "@/lib/local/store";
import type { DocumentItem, Job, RunEvent, RunOptions } from "@/lib/types";

interface PlannedSearch {
  index: number;
  source: string;
  name: string;
  label: string;
  kind: "scraper" | "api" | "email";
}

interface Plan {
  searches: PlannedSearch[];
  skipped: { source: string; label: string; kind: PlannedSearch["kind"]; reason: string }[];
  window_hours: number;
  languages: string[];
  regions: string[];
}

interface SearchResult {
  ok: boolean;
  error?: string;
  /** The source cannot answer for a while (a spent quota), so the run skips it. */
  unavailable?: boolean;
  jobs: (Partial<Job> & { id: string })[];
  excluded: Record<string, unknown>[];
  counts: { discovered: number; kept: number; filtered: number; language_filtered: number };
}

interface FilePayload {
  name: string;
  mime: string;
  size: number;
  data: string;
}

type Listener = (events: RunEvent[], done: boolean) => void;

class Cancelled extends Error {}

const GROUPS = [
  { step: "scrape", title: "Web scraping", match: (s: PlannedSearch) => s.kind === "scraper" },
  {
    step: "boards",
    title: "Job boards",
    match: (s: PlannedSearch) => s.kind === "api" && s.source !== "adzuna",
  },
  { step: "adzuna", title: "Adzuna", match: (s: PlannedSearch) => s.source === "adzuna" },
] as const;
const MAX_CONSECUTIVE_FAILURES = 2;

export function payloadToBlob(file: FilePayload) {
  const bytes = Uint8Array.from(atob(file.data), (char) => char.charCodeAt(0));
  return new Blob([bytes], { type: file.mime });
}

class RunController {
  events: RunEvent[] = [];
  cancelled = false;
  done = false;
  listeners = new Set<Listener>();
  private saveTimer: number | undefined;

  constructor(
    public id: number,
    public record: store.LocalRun,
  ) {}

  emit(step: string | null, status: string, message: string, data: Record<string, unknown> = {}) {
    this.events.push({
      seq: this.events.length + 1,
      ts: new Date().toISOString(),
      step,
      status,
      message,
      data,
    });
    for (const listener of this.listeners) listener(this.events, this.done);
    window.clearTimeout(this.saveTimer);
    this.saveTimer = window.setTimeout(() => this.persist(), 800);
  }

  log(message: string, level: "info" | "warning" | "error" = "info", step: string | null = null) {
    this.emit(step, "log", message, { level });
  }

  check() {
    if (this.cancelled) throw new Cancelled();
  }

  async persist() {
    window.clearTimeout(this.saveTimer);
    this.record = { ...this.record, events: [...this.events] };
    await store.saveRun(this.record);
  }
}

let active: RunController | null = null;

export function activeRunId() {
  return active && !active.done ? active.id : null;
}

function warnBeforeLeaving(event: BeforeUnloadEvent) {
  event.preventDefault();
  event.returnValue = "";
}

export async function startRun(options: Partial<RunOptions>): Promise<number> {
  if (activeRunId() != null) {
    throw new ApiError(
      409,
      `Run ${active!.id} is still in progress. Wait for it to finish or cancel it first.`,
      {
        run_id: active!.id,
      },
    );
  }
  await store.settleOrphanRuns(null);
  const id = await store.createRun(options);
  const controller = new RunController(id, await store.getRunRecord(id));
  active = controller;
  window.addEventListener("beforeunload", warnBeforeLeaving);
  void execute(controller, options).finally(() =>
    window.removeEventListener("beforeunload", warnBeforeLeaving),
  );
  return id;
}

export function cancelRun(id: number) {
  if (!active || active.id !== id || active.done) return false;
  active.cancelled = true;
  active.emit(null, "cancelling", "Cancelling after the current search or CV finishes.");
  return true;
}

/** Live events of a run: the running one from memory, older ones from storage. */
export function subscribe(id: number, listener: Listener) {
  if (active && active.id === id) {
    const controller = active;
    controller.listeners.add(listener);
    listener(controller.events, controller.done);
    return () => controller.listeners.delete(listener);
  }
  let stopped = false;
  store
    .getRunRecord(id)
    .then((run) => !stopped && listener(run.events, true))
    .catch(() => !stopped && listener([], true));
  return () => {
    stopped = true;
  };
}

async function execute(run: RunController, options: Partial<RunOptions>) {
  const summary = {
    discovered: 0,
    new: 0,
    filtered: 0,
    tailored: 0,
    failed: 0,
    eligible: 0,
    language_filtered: 0,
    failures: [] as { job_id: string; title: string; reason: string }[],
    report_path: "",
    sources: {} as Record<string, unknown>,
  };
  let status: "succeeded" | "failed" | "cancelled" = "succeeded";
  let error = "";
  const scope = {
    sources: options.sources,
    regions: options.regions,
    roles: options.roles,
    languages: options.languages,
    time_window_hours: options.time_window_hours,
  };
  try {
    const plan = await api.post<Plan>("/api/search/plan", scope);
    run.log(
      `🚀 Searching ${plan.regions.join(", ") || "your default regions"} for jobs from the last ${plan.window_hours} hours.`,
    );

    const found = new Map<string, Partial<Job> & { id: string }>();
    const excluded: Record<string, unknown>[] = [];
    for (const group of GROUPS) {
      run.check();
      const searches = plan.searches.filter(group.match);
      const skipped = plan.skipped.filter((item) => group.match({ ...item, index: -1, name: item.label }));
      if (!searches.length) {
        const reasons = skipped.map((item) => `${item.label}: ${item.reason}`);
        run.emit(
          group.step,
          "skipped",
          reasons.length
            ? `${group.title} skipped. ${reasons.join("; ")}.`
            : `${group.title}: no sources selected for this run.`,
        );
        continue;
      }
      const names = [...new Set(searches.map((search) => search.name))].join(", ");
      run.emit(group.step, "started", `${searches.length} searches on ${names}`, {
        done: 0,
        total: searches.length,
      });
      const totals = { discovered: 0, new: 0, duplicates: 0, filtered: 0 };
      const perSource: Record<string, { new: number }> = {};
      const failures: Record<string, number> = {};
      const gaveUp = new Set<string>();
      let errors = 0;
      for (const [position, search] of searches.entries()) {
        run.check();
        const counts = (perSource[search.name] ??= { new: 0 });
        if (gaveUp.has(search.source)) {
          errors += 1;
        } else {
          run.log(`🔍 ${search.name}: ${search.label}`, "info", group.step);
          let result: SearchResult | null = null;
          try {
            result = await api.post<SearchResult>("/api/search/run", {
              ...scope,
              index: search.index,
              source: search.source,
              label: search.label,
            });
          } catch (exc) {
            if (exc instanceof ApiError && (exc.status === 409 || exc.status === 401)) throw exc;
            result = {
              ok: false,
              error: (exc as Error).message,
              jobs: [],
              excluded: [],
              counts: { discovered: 0, kept: 0, filtered: 0, language_filtered: 0 },
            };
          }
          if (!result.ok && result.unavailable) {
            // A spent quota (e.g. Le Forem's daily limit): one warning, then skip the source.
            errors += 1;
            gaveUp.add(search.source);
            run.log(`⚠️ ${search.name}: ${result.error} Skipping its searches in this run.`, "warning", group.step);
          } else if (!result.ok) {
            errors += 1;
            failures[search.source] = (failures[search.source] ?? 0) + 1;
            run.log(`❌ ${search.name} (${search.label}): ${result.error}`, "error", group.step);
            if (failures[search.source] >= MAX_CONSECUTIVE_FAILURES) {
              gaveUp.add(search.source);
              run.log(
                `⚠️ ${search.name} failed ${MAX_CONSECUTIVE_FAILURES} times in a row; skipping its remaining searches in this run.`,
                "warning",
                group.step,
              );
            }
          } else {
            failures[search.source] = 0;
            const { added, known } = await store.upsertJobs(result.jobs, run.id);
            for (const job of result.jobs) found.set(job.id, job);
            excluded.push(...result.excluded);
            totals.discovered += result.counts.discovered;
            totals.new += added;
            totals.duplicates += known;
            totals.filtered += result.counts.filtered + result.counts.language_filtered;
            summary.language_filtered += result.counts.language_filtered;
            counts.new += added;
            run.log(
              `🎯 [${search.name}] ${added} new job(s) | (${known} already known, ${result.counts.filtered + result.counts.language_filtered} filtered)`,
              "info",
              group.step,
            );
          }
        }
        run.emit(
          group.step,
          "progress",
          `${search.name} · ${search.label} (${position + 1} of ${searches.length})`,
          {
            done: position + 1,
            total: searches.length,
            ...totals,
            per_source: perSource,
          },
        );
      }
      summary.discovered += totals.discovered;
      summary.new += totals.new;
      summary.filtered += totals.filtered;
      let message = `${totals.new} new, ${totals.duplicates} already known, ${totals.filtered} filtered`;
      const bySource = Object.entries(perSource)
        .map(([name, item]) => `${name} ${item.new} new`)
        .join(" · ");
      if (bySource) message += ` (${bySource})`;
      if (errors) message += `. ${errors} of ${searches.length} searches failed or were skipped`;
      run.emit(group.step, errors ? "warning" : "succeeded", message, {
        ...totals,
        per_source: perSource,
        errors,
      });
    }
    run.check();

    // Filter: the jobs this run found that passed every filter on the server.
    run.emit("filter", "started", "Selecting eligible jobs");
    const stored = new Map((await store.allJobs()).map((job) => [job.id, job]));
    const eligible = [...found.keys()]
      .map((id) => stored.get(id))
      .filter((job): job is NonNullable<typeof job> => Boolean(job));
    summary.eligible = eligible.length;
    let filterMessage = `${eligible.length} eligible job${eligible.length === 1 ? "" : "s"} found in this run`;
    if (summary.language_filtered) filterMessage += `, ${summary.language_filtered} skipped for language`;
    run.emit("filter", "succeeded", filterMessage, {
      eligible: eligible.length,
      language_filtered: summary.language_filtered,
    });

    // Tailoring
    const toTailor = eligible.filter((job) => !job.cv_path).slice(0, options.max_tailor ?? undefined);
    if (options.dry_run) {
      run.emit("tailoring", "skipped", "Dry run: no CVs were tailored.");
    } else if (!toTailor.length) {
      run.emit("tailoring", "succeeded", "Every eligible job already has a CV.", { done: 0, total: 0 });
    } else {
      run.emit("tailoring", "started", `Tailoring ${toTailor.length} CV(s)`, {
        done: 0,
        total: toTailor.length,
      });
      let done = 0;
      let missingKey = false;
      for (const job of toTailor) {
        run.check();
        run.log(`⚡ Tailoring CV: ${job.title} at ${job.company}`, "info", "tailoring");
        try {
          const result = await api.post<{ role_family: string; file: FilePayload }>("/api/tailor", { job });
          const doc = await store.saveDocument({
            kind: "cv",
            name: result.file.name,
            blob: payloadToBlob(result.file),
            job_id: job.id,
            role_family: result.role_family,
            run_id: run.id,
          });
          await store.updateJob(job.id, {
            cv_path: doc.path,
            status: "processed",
            role_family: result.role_family || job.role_family,
          });
          summary.tailored += 1;
        } catch (exc) {
          if (exc instanceof ApiError && exc.status === 400 && /Groq API key/i.test(exc.message)) {
            missingKey = true;
            run.log(exc.message, "warning", "tailoring");
            break;
          }
          if (exc instanceof ApiError && exc.status === 401) throw exc;
          summary.failures.push({
            job_id: job.id,
            title: job.title,
            reason: (exc as Error).message.replace(/^Tailoring failed: /, ""),
          });
        }
        done += 1;
        run.emit("tailoring", "progress", `Tailored ${done} of ${toTailor.length}`, {
          done,
          total: toTailor.length,
          job_id: job.id,
        });
      }
      summary.failed = summary.failures.length;
      if (missingKey) {
        run.emit(
          "tailoring",
          "skipped",
          "Your Groq API key is missing or invalid, so no CVs were tailored.",
          { action: "configure_groq" },
        );
      } else {
        let message = `Tailored ${summary.tailored} of ${toTailor.length} CVs.`;
        if (summary.failures.length) {
          const reasons = [...new Set(summary.failures.map((failure) => failure.reason))];
          message += ` ${summary.failed} failed: ${reasons.join("; ")}.`;
        }
        run.emit("tailoring", summary.failures.length ? "warning" : "succeeded", message, {
          done,
          total: toTailor.length,
          failures: summary.failures,
        });
      }
    }
    run.check();

    // Report
    run.emit("report", "started", "Writing the Excel report");
    const latest = new Map((await store.allJobs()).map((job) => [job.id, job]));
    const reportJobs = eligible.map((job) => {
      const current = latest.get(job.id) ?? job;
      // Links relative to the report: Reports/x.xlsx -> ../CVs/y.docx; in output/ both sit side by side.
      const cv = current.cv_path;
      const link = !cv ? "" : cv.startsWith("output/") ? cv.slice("output/".length) : `../${cv}`;
      return { ...current, cv_path: link };
    });
    const report = await api.post<{ file: FilePayload }>("/api/report", { jobs: reportJobs, excluded });
    const doc: DocumentItem = await store.saveDocument({
      kind: "report",
      name: report.file.name,
      blob: payloadToBlob(report.file),
      run_id: run.id,
    });
    summary.report_path = doc.path;
    run.log(`📊 Excel report saved: ${doc.path}`, "info", "report");
    run.emit("report", "succeeded", `Report saved with ${eligible.length} jobs`, {
      path: doc.path,
      document_id: doc.id,
    });
  } catch (exc) {
    if (exc instanceof Cancelled) {
      status = "cancelled";
      error = "Cancelled by you.";
      run.emit(null, "cancelled", "Run cancelled. Work finished before the cancel was kept.");
    } else {
      status = "failed";
      error = (exc as Error).message || String(exc);
      run.emit(null, "failed", error);
    }
  } finally {
    run.record = {
      ...run.record,
      status,
      error,
      finished_at: new Date().toISOString(),
      discovered: summary.discovered,
      new: summary.new,
      filtered: summary.filtered,
      tailored: summary.tailored,
      failed: summary.failures.length,
      summary,
    };
    run.done = true;
    run.emit(null, "finished", `Run ${status}.`, { run_status: status });
    await run.persist();
    if (active === run) active = null;
    window.dispatchEvent(new CustomEvent("local-run-finished", { detail: { id: run.id } }));
  }
}
