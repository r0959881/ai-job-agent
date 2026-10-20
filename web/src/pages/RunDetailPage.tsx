import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DocumentDownload } from "@/features/documents/DocumentDownload";
import { ArrowLeft, FileSpreadsheet, FileText, Square } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader, RelativeTime, RunStatusBadge } from "@/components/common";
import { useConfirm } from "@/components/confirm";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import { DocumentPreviewDialog } from "@/features/documents/DocumentPreviewDialog";
import { LogConsole } from "@/features/runs/LogConsole";
import { RunStepper } from "@/features/runs/RunStepper";
import { reduceSteps, settleSteps, toLogLines } from "@/features/runs/runSteps";
import { useRunEvents } from "@/features/runs/useRunEvents";
import { runSummaryText } from "@/features/runs/RunNotifier";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { DocumentItem, Run } from "@/lib/types";
import { formatAbsolute, formatDuration, parseDate } from "@/lib/utils";

function useNow(active: boolean) {
  const [now, setNow] = React.useState(Date.now());
  React.useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

export default function RunDetailPage() {
  const runId = Number(useParams().id);
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [previewDoc, setPreviewDoc] = React.useState<DocumentItem | null>(null);
  const run = useQuery({ queryKey: keys.run(runId), queryFn: () => api.get<Run>(`/api/runs/${runId}`) });
  const { events, ended } = useRunEvents(Number.isFinite(runId) ? runId : null);
  const running = run.data?.status === "running" && !ended;
  const now = useNow(running);

  React.useEffect(() => {
    if (ended) {
      queryClient.invalidateQueries({ queryKey: keys.run(runId) });
      queryClient.invalidateQueries({ queryKey: keys.runs });
    }
  }, [ended, runId, queryClient]);

  const cancel = useMutation({
    mutationFn: () => api.post(`/api/runs/${runId}/cancel`),
    onSuccess: () =>
      toast.info("Cancelling", { description: "The run stops after the current step or job finishes." }),
    onError: (error: Error) => toast.error("Could not cancel", { description: error.message }),
  });

  const status = ended ? ((events.at(-1)?.data?.run_status as string) ?? run.data?.status) : run.data?.status;
  const steps = React.useMemo(
    () => settleSteps(events.length ? reduceSteps(events) : (run.data?.steps ?? []), status ?? "running"),
    [events, run.data?.steps, status],
  );
  const lines = React.useMemo(() => toLogLines(events), [events]);
  const cancelling = events.some((event) => event.status === "cancelling");

  if (run.isPending) return <SkeletonRows rows={10} />;
  if (run.isError)
    return (
      <ErrorState
        title={`Run #${runId} could not be loaded`}
        error={run.error}
        onRetry={() => run.refetch()}
      />
    );

  const data = run.data;
  const started = parseDate(data.started_at);
  const elapsed = running && started ? (now - started.getTime()) / 1000 : data.duration_seconds;

  return (
    <>
      <Link
        to="/runs"
        className="mb-3 inline-flex items-center gap-1 text-body text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> All runs
      </Link>
      <PageHeader
        title={`Run #${data.id}`}
        description={
          <span className="tabular">
            Started <RelativeTime value={data.started_at} /> · {formatAbsolute(data.started_at)}
            {elapsed != null && ` · ${formatDuration(elapsed)}`}
          </span>
        }
        actions={
          <>
            <RunStatusBadge status={status ?? data.status} />
            {running && (
              <Button
                variant="danger"
                loading={cancel.isPending}
                disabled={cancelling}
                onClick={async () => {
                  const ok = await confirm({
                    title: "Cancel this run?",
                    description:
                      "The current step or CV finishes first. Jobs and CVs already saved are kept.",
                    confirmLabel: "Cancel run",
                    destructive: true,
                  });
                  if (ok) cancel.mutate();
                }}
              >
                <Square /> {cancelling ? "Cancelling…" : "Cancel run"}
              </Button>
            )}
          </>
        }
      />
      {!running && status !== "running" && (
        <Card className="mb-6">
          <CardContent className="flex flex-wrap items-center gap-x-8 gap-y-2 pt-4 tabular">
            <p className="w-full text-body">
              {runSummaryText({ ...data, status: (status as Run["status"]) ?? data.status })}
            </p>
            {[
              ["Found", data.discovered],
              ["New", data.new],
              ["Filtered", data.filtered],
              ["Eligible", data.summary?.eligible ?? 0],
              ["CVs tailored", data.tailored],
              ["Failed", data.failed],
            ].map(([label, value]) => (
              <div key={label as string}>
                <p className="text-caption text-muted-foreground">{label}</p>
                <p className="text-title">{value}</p>
              </div>
            ))}
            {data.summary?.failures?.length ? (
              <ul className="w-full list-disc pl-5 text-body text-danger">
                {data.summary.failures.map((failure) => (
                  <li key={failure.job_id}>
                    <Link className="underline" to={`/jobs/${failure.job_id}`}>
                      {failure.title}
                    </Link>
                    : {failure.reason}
                  </li>
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>
      )}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Steps</CardTitle>
          </CardHeader>
          <CardContent>
            <RunStepper steps={steps} now={now} />
          </CardContent>
        </Card>
        <div className="min-w-0 space-y-6">
          <LogConsole lines={lines} live={running} />
          {!running && (
            <Card>
              <CardHeader>
                <CardTitle>Documents from this run</CardTitle>
              </CardHeader>
              <CardContent>
                {data.documents?.length ? (
                  <ul className="divide-y">
                    {data.documents.map((doc) => (
                      <li key={doc.id} className="flex items-center gap-3 py-2">
                        {doc.kind === "report" ? (
                          <FileSpreadsheet className="size-4 text-success" />
                        ) : (
                          <FileText className="size-4 text-info" />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate">
                            {doc.job_title ? `${doc.job_title} · ${doc.job_company}` : doc.name}
                          </p>
                          <p className="truncate text-caption text-muted-foreground">{doc.name}</p>
                        </div>
                        {doc.kind !== "report" && doc.exists && (
                          <Button size="sm" variant="ghost" onClick={() => setPreviewDoc(doc)}>
                            Preview
                          </Button>
                        )}
                        {doc.exists ? (
                          <DocumentDownload
                            className={buttonVariants({ size: "sm", variant: "outline" })}
                            id={doc.id}
                          >
                            Download
                          </DocumentDownload>
                        ) : (
                          <span className="text-caption text-muted-foreground">File deleted</span>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState
                    title="No documents"
                    description="This run did not tailor any CVs."
                    className="py-6"
                  />
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
      <DocumentPreviewDialog document={previewDoc} onOpenChange={(open) => !open && setPreviewDoc(null)} />
    </>
  );
}
