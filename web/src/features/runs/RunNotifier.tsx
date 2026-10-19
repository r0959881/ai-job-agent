import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { keys, useRunsList } from "@/lib/queries";
import type { Run } from "@/lib/types";

export function runSummaryText(run: Run) {
  if (run.status === "failed") return run.error || "The run failed.";
  if (run.status === "cancelled") return `Cancelled. ${run.tailored} CV(s) were tailored before stopping.`;
  const parts = [`${run.new} new job(s)`, `${run.tailored} CV(s) tailored`];
  if (run.failed) parts.push(`${run.failed} failed`);
  return parts.join(", ") + ".";
}

/** Toasts (and a browser notification when the tab is hidden) when an active run finishes. */
export function RunNotifier() {
  const { data } = useRunsList(10);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const previous = React.useRef<number | null>(null);

  React.useEffect(() => {
    const active = data?.active_id ?? null;
    const finished = previous.current;
    previous.current = active;
    if (finished == null || active === finished) return;
    api
      .get<Run>(`/api/runs/${finished}`)
      .then((run) => {
        queryClient.invalidateQueries({ queryKey: ["jobs"] });
        queryClient.invalidateQueries({ queryKey: ["documents"] });
        queryClient.invalidateQueries({ queryKey: keys.stats });
        const title = `Run #${run.id} ${run.status}`;
        const description = runSummaryText(run);
        const show = run.status === "succeeded" ? toast.success : run.status === "failed" ? toast.error : toast.warning;
        show(title, { description, action: { label: "View", onClick: () => navigate(`/runs/${run.id}`) } });
        if (document.hidden && "Notification" in window && Notification.permission === "granted") {
          const note = new Notification(title, { body: description, tag: `run-${run.id}` });
          note.onclick = () => {
            window.focus();
            navigate(`/runs/${run.id}`);
          };
        }
      })
      .catch(() => undefined);
  }, [data?.active_id, navigate, queryClient]);

  return null;
}
