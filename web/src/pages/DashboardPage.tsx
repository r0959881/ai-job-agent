import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Briefcase, CheckCircle2, CircleSlash, FileText, Play, Send, Users, XCircle } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageHeader, RelativeTime, RunStatusBadge } from "@/components/common";
import { useStartRun } from "@/components/layout/RunControl";
import { EmptyState, ErrorState, SkeletonCards, SkeletonRows } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import { Tooltip } from "@/components/ui/overlays";
import { GmailAttentionBanner } from "@/features/integrations/GmailAttentionBanner";
import { runSummaryText } from "@/features/runs/RunNotifier";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { HealthLevel, IntegrationHealth, ResumeResponse, Stats } from "@/lib/types";
import { cn, formatDuration } from "@/lib/utils";

function StatTile({ label, value, hint, icon: Icon, to }: { label: string; value: number; hint: string; icon: typeof Briefcase; to: string }) {
  return (
    <Link to={to} className="group rounded-lg focus-visible:outline-none">
      <Card className="h-full p-4 transition-colors group-hover:bg-muted/40">
        <div className="flex items-center justify-between text-body text-muted-foreground">
          {label}
          <Icon className="size-4" aria-hidden />
        </div>
        <p className="mt-2 text-[2rem] font-semibold leading-none tabular">{value}</p>
        <p className="mt-2 text-caption text-muted-foreground">{hint}</p>
      </Card>
    </Link>
  );
}

/** Single-series horizontal bars: one accent hue, direct count labels, step conversion in text. */
function Funnel({ steps }: { steps: Stats["funnel"] }) {
  const max = Math.max(1, ...steps.map((s) => s.count));
  return (
    <ol className="space-y-3" aria-label="Application funnel">
      {steps.map((step, index) => {
        const previous = index ? steps[index - 1].count : null;
        const rate = previous ? Math.round((step.count / previous) * 100) : null;
        const tip = `${step.label}: ${step.count}${rate != null ? ` (${rate}% of ${steps[index - 1].label.toLowerCase()})` : ""}`;
        return (
          <li key={step.key} className="grid grid-cols-[7rem_1fr_4.5rem] items-center gap-3">
            <span className="text-body">{step.label}</span>
            <Tooltip content={tip}>
              <div className="h-6 rounded-sm bg-muted" tabIndex={0} aria-label={tip}>
                <div
                  className="h-full rounded-r bg-primary transition-[width] duration-200"
                  style={{ width: `${Math.max((step.count / max) * 100, step.count ? 1 : 0)}%` }}
                />
              </div>
            </Tooltip>
            <span className="text-right text-body tabular">
              <span className="font-semibold">{step.count}</span>
              {rate != null && <span className="ml-1 text-caption text-muted-foreground">{rate}%</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

const HEALTH: Record<HealthLevel, { icon: typeof CheckCircle2; className: string; label: string }> = {
  ok: { icon: CheckCircle2, className: "bg-success-soft text-success", label: "Healthy" },
  warning: { icon: AlertTriangle, className: "bg-warning-soft text-warning", label: "Needs attention" },
  error: { icon: XCircle, className: "bg-danger-soft text-danger", label: "Error" },
  missing: { icon: CircleSlash, className: "bg-muted text-muted-foreground", label: "Not set up" },
};

export function HealthChip({ name, health }: { name: string; health: IntegrationHealth }) {
  const { icon: Icon, className, label } = HEALTH[health.status];
  const chip = (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-caption font-medium", className)}>
      <Icon className="size-3.5" aria-hidden /> {name}
      <span className="sr-only">: {label}. {health.message}</span>
    </span>
  );
  return (
    <Tooltip content={health.message}>
      {health.status !== "ok" && health.action ? (
        <Link to={health.action} className="rounded-full">
          {chip}
        </Link>
      ) : (
        <span tabIndex={0} className="rounded-full">{chip}</span>
      )}
    </Tooltip>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const startRun = useStartRun();
  const stats = useQuery({ queryKey: keys.stats, queryFn: () => api.get<Stats>("/api/stats"), refetchInterval: 30_000 });
  const resume = useQuery({ queryKey: keys.resume, queryFn: () => api.get<ResumeResponse>("/api/resume") });

  // First launch with an empty resume goes to onboarding (once; it can be dismissed).
  React.useEffect(() => {
    let dismissed = false;
    try {
      dismissed = localStorage.getItem("onboarding-dismissed") === "1";
    } catch {
      /* ignore */
    }
    if (resume.data?.empty && !dismissed) navigate("/onboarding", { replace: true });
  }, [resume.data?.empty, navigate]);

  const data = stats.data;
  const lastRun = data?.last_run;
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your job search at a glance."
        actions={
          <Button onClick={startRun}>
            <Play /> Run agent
          </Button>
        }
      />
      <GmailAttentionBanner />
      {stats.isError && <ErrorState error={stats.error} onRetry={() => stats.refetch()} />}
      {stats.isPending ? (
        <SkeletonCards />
      ) : data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Jobs found" value={data.jobs_last_window} hint={`Posted or found in the last ${data.window_hours}h`} icon={Briefcase} to="/jobs" />
          <StatTile label="CVs generated" value={data.cvs_generated} hint="Tailored CVs in the output folder" icon={FileText} to="/documents?kind=cv" />
          <StatTile label="Applications sent" value={data.applications_sent} hint="Marked as applied or later" icon={Send} to="/jobs?application_status=applied&application_status=interviewing&application_status=offer&application_status=rejected" />
          <StatTile label="Interviews" value={data.interviews} hint="Interviewing or with an offer" icon={Users} to="/jobs?application_status=interviewing&application_status=offer" />
        </div>
      ) : null}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Funnel</CardTitle>
          </CardHeader>
          <CardContent>{data ? <Funnel steps={data.funnel} /> : <SkeletonRows rows={5} />}</CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Last run</CardTitle>
            {lastRun && <RunStatusBadge status={lastRun.status} />}
          </CardHeader>
          <CardContent className="space-y-3">
            {!data ? (
              <SkeletonRows rows={4} />
            ) : !lastRun ? (
              <EmptyState title="No runs yet" description="Run the agent to find jobs and tailor CVs." className="py-6" action={<Button size="sm" onClick={startRun}>Run agent</Button>} />
            ) : (
              <>
                <p className="text-body text-muted-foreground tabular">
                  #{lastRun.id} · <RelativeTime value={lastRun.started_at} />
                  {lastRun.duration_seconds != null && ` · ${formatDuration(lastRun.duration_seconds)}`}
                </p>
                <p className="text-body">{runSummaryText(lastRun)}</p>
                <ul className="grid grid-cols-3 gap-2 text-body tabular">
                  {(lastRun.steps ?? [])
                    .filter((s) => ["adzuna", "arbeitnow", "gmail"].includes(s.step))
                    .map((s) => (
                      <li key={s.step} className="rounded-md border p-2">
                        <p className="text-caption text-muted-foreground">{s.label}</p>
                        <p className="font-medium">{s.status === "skipped" ? "Skipped" : `${(s.data.new as number) ?? 0} new`}</p>
                      </li>
                    ))}
                </ul>
                <Link to={`/runs/${lastRun.id}`} className={buttonVariants({ variant: "link", size: "sm" })}>
                  View log <ArrowRight />
                </Link>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Ready to apply</CardTitle>
            <Link to="/jobs?quick=ready" className={buttonVariants({ variant: "link", size: "sm" })}>
              See all <ArrowRight />
            </Link>
          </CardHeader>
          <CardContent>
            {!data ? (
              <SkeletonRows rows={4} />
            ) : data.ready_to_apply.length === 0 ? (
              <EmptyState title="Nothing waiting" description="Jobs with a tailored CV that you have not applied to show up here." className="py-6" />
            ) : (
              <ul className="divide-y">
                {data.ready_to_apply.map((job) => (
                  <li key={job.id}>
                    <Link to={`/jobs/${job.id}`} className="flex items-center gap-3 rounded-md px-2 py-2.5 hover:bg-muted/60">
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">{job.title}</p>
                        <p className="truncate text-caption text-muted-foreground">
                          {job.company} · {job.location}
                        </p>
                      </div>
                      <RelativeTime value={job.posted_at || job.discovered_at} className="shrink-0 text-caption text-muted-foreground" />
                      <span className="text-body font-medium text-primary">Apply</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Integrations</CardTitle>
          </CardHeader>
          <CardContent>
            {data ? (
              <div className="flex flex-wrap gap-2">
                <HealthChip name="Groq" health={data.integrations.groq} />
                <HealthChip name="Adzuna" health={data.integrations.adzuna} />
                <HealthChip name="Gmail" health={data.integrations.gmail} />
                <HealthChip name="Email alerts" health={data.integrations.smtp} />
              </div>
            ) : (
              <SkeletonRows rows={2} />
            )}
            <Link to="/settings/integrations" className={cn(buttonVariants({ variant: "link", size: "sm" }), "mt-2 px-0")}>
              Manage integrations <ArrowRight />
            </Link>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
