import { Loader2, Play } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { StartRunDialog } from "@/features/runs/StartRunDialog";
import { Button } from "@/components/ui/button";
import { useRunsList } from "@/lib/queries";
import type { RunStep } from "@/lib/types";

const RunDialogContext = React.createContext<(() => void) | null>(null);

/** Lets any page (dashboard, command palette, onboarding) open the Start-run dialog. */
export function RunDialogProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const openDialog = React.useCallback(() => setOpen(true), []);
  return (
    <RunDialogContext.Provider value={openDialog}>
      {children}
      <StartRunDialog open={open} onOpenChange={setOpen} />
    </RunDialogContext.Provider>
  );
}

export function useStartRun() {
  const open = React.useContext(RunDialogContext);
  if (!open) throw new Error("useStartRun must be used inside RunDialogProvider");
  return open;
}

export function describeActiveStep(steps?: RunStep[]) {
  const running = steps?.find((step) => step.status === "running");
  if (!running) return "Starting…";
  const done = running.data?.done as number | undefined;
  const total = running.data?.total as number | undefined;
  return total ? `${running.label} ${done ?? 0}/${total}` : running.label;
}

export function RunControl() {
  const openStartRun = useStartRun();
  const { data } = useRunsList(10);
  const active = data?.active;
  if (data?.active_id) {
    return (
      <Link
        to={`/runs/${data.active_id}`}
        className="inline-flex h-9 items-center gap-2 rounded-full border border-info/40 bg-info-soft px-3 text-body font-medium text-info transition-colors hover:bg-info-soft/70"
        aria-live="polite"
      >
        <Loader2 className="size-4 animate-spin" aria-hidden />
        <span className="tabular">Run #{data.active_id}: {describeActiveStep(active?.steps)}</span>
      </Link>
    );
  }
  return (
    <Button onClick={openStartRun}>
      <Play /> Run agent
    </Button>
  );
}
