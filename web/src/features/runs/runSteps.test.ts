import { reduceSteps, settleSteps, toLogLines } from "@/features/runs/runSteps";
import type { RunEvent } from "@/lib/types";

let seq = 0;
const ev = (
  step: string | null,
  status: string,
  message = "",
  data: Record<string, unknown> = {},
): RunEvent => ({
  seq: ++seq,
  ts: new Date(2026, 0, 1, 12, 0, seq).toISOString(),
  step,
  status,
  message,
  data,
});

describe("reduceSteps", () => {
  it("tracks each step's status, progress and counts", () => {
    const events = [
      ev("init_db", "started"),
      ev("init_db", "succeeded", "Database ready"),
      ev("adzuna", "skipped", "Adzuna credentials are missing"),
      ev("tailoring", "started", "Tailoring 3 CV(s)", { done: 0, total: 3 }),
      ev("tailoring", "log", "🤖 Tailoring CV for: X", { level: "info" }),
      ev("tailoring", "progress", "Tailored 1 of 3", { done: 1, total: 3 }),
    ];
    const steps = reduceSteps(events);
    const byName = Object.fromEntries(steps.map((s) => [s.step, s]));
    expect(steps.map((s) => s.step)).toEqual([
      "init_db",
      "adzuna",
      "arbeitnow",
      "gmail",
      "filter",
      "tailoring",
      "report",
    ]);
    expect(byName.init_db.status).toBe("succeeded");
    expect(byName.adzuna.status).toBe("skipped");
    expect(byName.arbeitnow.status).toBe("pending");
    expect(byName.tailoring.status).toBe("running");
    expect(byName.tailoring.data).toMatchObject({ done: 1, total: 3 });
  });

  it("marks steps left running as stopped once a run is cancelled", () => {
    const steps = settleSteps(reduceSteps([ev("tailoring", "started")]), "cancelled");
    expect(steps.find((s) => s.step === "tailoring")?.status).toBe("skipped");
  });
});

describe("toLogLines", () => {
  it("keeps log lines with levels and step outcomes, drops progress", () => {
    const lines = toLogLines([
      ev("adzuna", "log", "🔍 Searching", { level: "info" }),
      ev("adzuna", "progress", "Query 1 of 2"),
      ev("gmail", "warning", "Gmail skipped"),
      ev("tailoring", "log", "❌ Error", { level: "error" }),
    ]);
    expect(lines.map((l) => [l.level, l.text])).toEqual([
      ["info", "🔍 Searching"],
      ["warning", "Gmail skipped"],
      ["error", "❌ Error"],
    ]);
  });
});
