import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { Run } from "@/lib/types";

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Plain, specific one-line outcome, e.g. "Tailored 4 of 6 CVs. 2 failed because Groq timed out." */
export function runSummaryText(run: Run) {
  if (run.status === "failed") return run.error || "The run failed before it finished.";
  const found = `Found ${plural(run.new, "new job")}`;
  if (run.status === "cancelled")
    return `Cancelled by you. ${found}; ${plural(run.tailored, "CV")} tailored before stopping.`;
  if (run.options?.dry_run) {
    return `Dry run: ${found.toLowerCase()} and ${run.summary?.eligible ?? 0} eligible in the time window. No CVs were tailored.`;
  }
  const attempted = run.tailored + run.failed;
  if (!attempted) return `${found}. Every eligible job already had a CV.`;
  const reasons = [...new Set((run.summary?.failures ?? []).map((f) => f.reason))];
  const failed = run.failed ? ` ${run.failed} failed because ${reasons.join(", ") || "of an error"}.` : "";
  return `${found}. Tailored ${run.tailored} of ${plural(attempted, "CV")}.${failed}`;
}

/** Toasts (and a browser notification when the tab is hidden) when an active run finishes. */
export function RunNotifier() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  React.useEffect(() => {
    const onFinished = (event: Event) => {
      const finished = (event as CustomEvent<{ id: number }>).detail.id;
      api
        .get<Run>(`/api/runs/${finished}`)
        .then((run) => {
          queryClient.invalidateQueries({ queryKey: ["jobs"] });
          queryClient.invalidateQueries({ queryKey: ["documents"] });
          queryClient.invalidateQueries({ queryKey: keys.stats });
          const title = `Run #${run.id} ${run.status}`;
          const description = runSummaryText(run);
          const show =
            run.status === "succeeded"
              ? toast.success
              : run.status === "failed"
                ? toast.error
                : toast.warning;
          // A run that found jobs leads to them on the New jobs page; otherwise to the run's log.
          const action = run.new
            ? { label: "See new jobs", onClick: () => navigate("/jobs/new") }
            : { label: "View", onClick: () => navigate(`/runs/${run.id}`) };
          show(title, { description, action });
          if (document.hidden && "Notification" in window && Notification.permission === "granted") {
            const note = new Notification(title, { body: description, tag: `run-${run.id}` });
            note.onclick = () => {
              window.focus();
              navigate(`/runs/${run.id}`);
            };
          }
        })
        .catch(() => undefined);
    };
    window.addEventListener("local-run-finished", onFinished);
    return () => window.removeEventListener("local-run-finished", onFinished);
  }, [navigate, queryClient]);

  return null;
}
