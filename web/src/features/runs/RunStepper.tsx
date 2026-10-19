import { AlertTriangle, CheckCircle2, Circle, CircleSlash, Loader2, XCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { buttonVariants } from "@/components/ui/button";
import { Progress } from "@/components/ui/primitives";
import type { RunStep, StepStatus } from "@/lib/types";
import { cn, formatDuration, parseDate } from "@/lib/utils";

const ICONS: Record<StepStatus, { icon: typeof Circle; className: string; label: string }> = {
  pending: { icon: Circle, className: "text-muted-foreground", label: "Waiting" },
  running: { icon: Loader2, className: "animate-spin text-info", label: "Running" },
  succeeded: { icon: CheckCircle2, className: "text-success", label: "Done" },
  warning: { icon: AlertTriangle, className: "text-warning", label: "Finished with a warning" },
  failed: { icon: XCircle, className: "text-danger", label: "Failed" },
  skipped: { icon: CircleSlash, className: "text-muted-foreground", label: "Skipped" },
};

function stepDuration(step: RunStep, now: number) {
  const start = parseDate(step.started_at);
  if (!start) return "";
  const end = parseDate(step.finished_at)?.getTime() ?? (step.status === "running" ? now : null);
  return end ? formatDuration((end - start.getTime()) / 1000) : "";
}

const ACTIONS: Record<string, { label: string; to: string }> = {
  reconnect_gmail: { label: "Reconnect Gmail", to: "/settings/integrations#gmail" },
  configure_groq: { label: "Add Groq key", to: "/settings/integrations" },
};

export function RunStepper({ steps, now = Date.now() }: { steps: RunStep[]; now?: number }) {
  return (
    <ol className="space-y-0" aria-label="Run steps">
      {steps.map((step, index) => {
        const { icon: Icon, className, label } = ICONS[step.status];
        const done = step.data.done as number | undefined;
        const total = step.data.total as number | undefined;
        const action = ACTIONS[String(step.data.action ?? "")];
        const title = step.step === "tailoring" && total ? `${step.label} ${done ?? 0}/${total}` : step.label;
        return (
          <li key={step.step} className="relative flex gap-3 pb-5 last:pb-0">
            {index < steps.length - 1 && (
              <span aria-hidden className="absolute left-[11px] top-7 h-[calc(100%-1.5rem)] w-px bg-border" />
            )}
            <Icon className={cn("mt-0.5 size-6 shrink-0", className)} aria-label={label} />
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span
                  className={cn("font-medium tabular", step.status === "pending" && "text-muted-foreground")}
                >
                  {title}
                </span>
                <span className="text-caption text-muted-foreground tabular">{stepDuration(step, now)}</span>
              </div>
              {step.message && step.status !== "pending" && (
                <p
                  className={cn(
                    "text-body text-muted-foreground",
                    step.status === "warning" && "text-warning",
                    step.status === "failed" && "text-danger",
                  )}
                >
                  {step.message}
                </p>
              )}
              {step.status === "running" && total ? (
                <Progress
                  value={((done ?? 0) / total) * 100}
                  aria-label={`${step.label} progress`}
                  className="max-w-sm"
                />
              ) : null}
              {action && (
                <Link to={action.to} className={buttonVariants({ size: "sm", variant: "outline" })}>
                  {action.label}
                </Link>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
