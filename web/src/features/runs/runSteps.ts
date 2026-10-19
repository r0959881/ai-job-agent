import type { RunEvent, RunStep, StepStatus } from "@/lib/types";

export const STEPS: { step: string; label: string }[] = [
  { step: "init_db", label: "Init DB" },
  { step: "adzuna", label: "Adzuna" },
  { step: "arbeitnow", label: "Arbeitnow" },
  { step: "gmail", label: "Gmail" },
  { step: "filter", label: "Filter" },
  { step: "tailoring", label: "Tailoring" },
  { step: "report", label: "Report" },
];

const FINAL: StepStatus[] = ["succeeded", "warning", "failed", "skipped"];

/** Collapse a run's event stream into one state per step (mirrors api/services/runs.step_summary). */
export function reduceSteps(events: RunEvent[]): RunStep[] {
  const steps = new Map<string, RunStep>(
    STEPS.map(({ step, label }) => [
      step,
      { step, label, status: "pending", message: "", started_at: null, finished_at: null, data: {} },
    ]),
  );
  for (const event of events) {
    const current = event.step ? steps.get(event.step) : undefined;
    if (!current || event.status === "log") continue;
    if (event.status === "started") {
      Object.assign(current, { status: "running", started_at: event.ts, message: event.message });
    } else if (event.status === "progress") {
      current.status = "running";
      current.message = event.message;
      current.started_at ??= event.ts;
    } else if ((FINAL as string[]).includes(event.status)) {
      Object.assign(current, {
        status: event.status as StepStatus,
        finished_at: event.ts,
        message: event.message,
      });
      current.started_at ??= event.ts;
    }
    current.data = { ...current.data, ...event.data };
  }
  return [...steps.values()];
}

/** When a run ends early (cancel/failure), steps still "running" are shown as stopped. */
export function settleSteps(steps: RunStep[], runStatus: string): RunStep[] {
  if (runStatus === "running") return steps;
  return steps.map((step) =>
    step.status === "running" ? { ...step, status: runStatus === "cancelled" ? "skipped" : "failed" } : step,
  );
}

export type LogLevel = "info" | "warning" | "error";

export interface LogLine {
  seq: number;
  ts: string;
  level: LogLevel;
  step: string | null;
  text: string;
}

export function toLogLines(events: RunEvent[]): LogLine[] {
  const lines: LogLine[] = [];
  for (const event of events) {
    if (event.status === "progress" || event.status === "started") continue;
    if (!event.message) continue;
    let level: LogLevel = "info";
    if (event.status === "log") {
      const raw = String(event.data?.level ?? "info");
      level = raw === "error" ? "error" : raw === "warning" ? "warning" : "info";
    } else if (event.status === "failed") level = "error";
    else if (event.status === "warning" || event.status === "cancelling" || event.status === "cancelled")
      level = "warning";
    lines.push({ seq: event.seq, ts: event.ts, level, step: event.step, text: event.message });
  }
  return lines;
}
