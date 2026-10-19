import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Calendar, Download, ExternalLink, Eye, FileText, MapPin, Trash2, Wallet } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ApplicationStatusBadge, RelativeTime, SourceBadge } from "@/components/common";
import { useConfirm } from "@/components/confirm";
import { EmptyState, ErrorState, SkeletonForm } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/controls";
import { Card } from "@/components/ui/primitives";
import { DocumentPreviewDialog } from "@/features/documents/DocumentPreviewDialog";
import { ApplyWorkspace } from "@/features/jobs/ApplyWorkspace";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { DocumentItem, JobDetail } from "@/lib/types";
import { formatAbsolute, formatSalary } from "@/lib/utils";

/** Highlight resume keywords inside the plain-text description. */
function HighlightedText({ text, words }: { text: string; words: string[] }) {
  const clean = text.replace(/<[^>]+>/g, " ").replace(/\s+\n/g, "\n");
  if (!words.length) return <>{clean}</>;
  const pattern = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return (
    <>
      {clean.split(pattern).map((part, index) =>
        index % 2 ? (
          <mark key={index} className="rounded bg-success-soft px-0.5 text-success">
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  );
}

export default function JobDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "apply";
  const [preview, setPreview] = React.useState<DocumentItem | null>(null);
  const job = useQuery({ queryKey: keys.job(id), queryFn: () => api.get<JobDetail>(`/api/jobs/${id}`) });

  const remove = useMutation({
    mutationFn: (deleteFiles: boolean) => api.delete(`/api/jobs/${id}?delete_files=${deleteFiles}`),
    onSuccess: () => {
      toast.success("Job deleted");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      navigate("/jobs");
    },
    onError: (error: Error) => toast.error("The job was not deleted", { description: error.message }),
  });

  if (job.isPending) return <SkeletonForm fields={8} />;
  if (job.isError) {
    return (
      <>
        <Link to="/jobs" className="mb-3 inline-flex items-center gap-1 text-body text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> All jobs
        </Link>
        <ErrorState title="This job could not be loaded" error={job.error} onRetry={() => job.refetch()} />
      </>
    );
  }
  const data = job.data;
  const salary = formatSalary(data.salary_min, data.salary_max, data.salary_currency);
  const posted = data.posted_at || data.discovered_at;

  return (
    <>
      <Link to="/jobs" className="mb-3 inline-flex items-center gap-1 text-body text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> All jobs
      </Link>
      <header className="mb-6 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <h1 className="text-title">{data.title}</h1>
            <p className="text-section font-normal text-muted-foreground">{data.company}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {data.url && (
              <a className={buttonVariants()} href={data.url} target="_blank" rel="noopener noreferrer">
                Open posting <ExternalLink />
              </a>
            )}
            <Button
              variant="outline"
              aria-label="Delete job"
              onClick={async () => {
                const ok = await confirm({
                  title: "Delete this job?",
                  description: `“${data.title}” and its ${data.documents.length} generated file(s) are removed. A future run may find the job again.`,
                  confirmLabel: "Delete job and files",
                  destructive: true,
                });
                if (ok) remove.mutate(true);
              }}
            >
              <Trash2 />
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-body text-muted-foreground">
          <span className="flex items-center gap-1.5"><MapPin className="size-4" /> {data.location || "Location unknown"}</span>
          {salary && <span className="flex items-center gap-1.5 tabular"><Wallet className="size-4" /> {salary}</span>}
          <span className="flex items-center gap-1.5"><Calendar className="size-4" /> Posted <RelativeTime value={posted} /></span>
          <SourceBadge source={data.source} />
          <ApplicationStatusBadge status={data.application_status} />
        </div>
      </header>

      <Tabs value={tab} onValueChange={(value) => setParams(value === "apply" ? {} : { tab: value }, { replace: true })}>
        <TabsList>
          <TabsTrigger value="apply">Apply</TabsTrigger>
          <TabsTrigger value="description">Description</TabsTrigger>
          <TabsTrigger value="documents">Documents ({data.documents.length})</TabsTrigger>
          <TabsTrigger value="notes">Notes & history</TabsTrigger>
        </TabsList>
        <TabsContent value="apply">
          <ApplyWorkspace job={data} />
        </TabsContent>
        <TabsContent value="description">
          <Card className="p-6">
            {data.description ? (
              <div className="max-w-prose whitespace-pre-line text-body leading-relaxed">
                <HighlightedText text={data.description} words={data.matched_keywords} />
              </div>
            ) : (
              <EmptyState title="No description stored" description="Open the posting to read the full text." />
            )}
          </Card>
        </TabsContent>
        <TabsContent value="documents">
          {data.documents.length === 0 ? (
            <EmptyState icon={FileText} title="No documents for this job yet" description="Generate a CV or cover letter on the Apply tab." />
          ) : (
            <Card className="divide-y">
              {data.documents.map((doc) => (
                <div key={doc.id} className="flex items-center gap-3 p-3">
                  <FileText className="size-4 text-info" />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{doc.kind === "cv" ? "Tailored CV" : doc.kind === "cover_letter" ? "Cover letter" : doc.name}</p>
                    <p className="truncate text-caption text-muted-foreground" title={formatAbsolute(doc.created_at)}>
                      {doc.name} · <RelativeTime value={doc.created_at} />
                    </p>
                  </div>
                  {doc.exists ? (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => setPreview(doc)}>
                        <Eye /> Preview
                      </Button>
                      <a className={buttonVariants({ size: "sm", variant: "outline" })} href={`/api/documents/${doc.id}/download`}>
                        <Download /> Download
                      </a>
                    </>
                  ) : (
                    <span className="text-caption text-muted-foreground">File deleted</span>
                  )}
                </div>
              ))}
            </Card>
          )}
        </TabsContent>
        <TabsContent value="notes">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="p-4">
              <h2 className="mb-2 text-section">Notes</h2>
              <p className="whitespace-pre-line text-body">{data.notes || <span className="text-muted-foreground">No notes yet. Add them in step 6 on the Apply tab.</span>}</p>
            </Card>
            <Card className="p-4">
              <h2 className="mb-2 text-section">History</h2>
              <ol className="space-y-2">
                {data.history.map((entry, index) => (
                  <li key={index} className="flex justify-between gap-3 text-body">
                    <span>{entry.text}</span>
                    <RelativeTime value={entry.at} className="shrink-0 text-muted-foreground" />
                  </li>
                ))}
              </ol>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
      <DocumentPreviewDialog document={preview} onOpenChange={(open) => !open && setPreview(null)} />
    </>
  );
}
