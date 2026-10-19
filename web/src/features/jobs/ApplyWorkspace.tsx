import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  CheckCircle2,
  Circle,
  Download,
  ExternalLink,
  Eye,
  FileText,
  Lightbulb,
  Pencil,
  RefreshCw,
  Send,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { APPLICATION_STATUS_OPTIONS, CopyButton, Field, RelativeTime } from "@/components/common";
import { useConfirm } from "@/components/confirm";
import { StringListEditor } from "@/components/sortable";
import { Button, buttonVariants } from "@/components/ui/button";
import { Select } from "@/components/ui/controls";
import { Badge, Card, Input, Textarea } from "@/components/ui/primitives";
import { DocumentPreviewDialog } from "@/features/documents/DocumentPreviewDialog";
import { humanize } from "@/features/profile/schema";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { DocumentItem, JobDetail, ResumeResponse, TailoredContent } from "@/lib/types";
import { cn } from "@/lib/utils";

type StepKey = "review" | "cv" | "cover_letter" | "answers" | "apply" | "track";

function useJobMutations(job: JobDetail) {
  const queryClient = useQueryClient();
  const setJob = (next: JobDetail) => {
    queryClient.setQueryData(keys.job(job.id), next);
    queryClient.invalidateQueries({ queryKey: ["jobs"] });
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: keys.stats });
  };
  const patch = useMutation({
    mutationFn: (changes: Partial<JobDetail>) => api.patch<JobDetail>(`/api/jobs/${job.id}`, changes),
    onMutate: async (changes) => {
      // Optimistic: checklist and status changes are safe to show immediately.
      const previous = queryClient.getQueryData<JobDetail>(keys.job(job.id));
      if (previous) queryClient.setQueryData(keys.job(job.id), { ...previous, ...changes });
      return { previous };
    },
    onError: (error: Error, _changes, context) => {
      if (context?.previous) queryClient.setQueryData(keys.job(job.id), context.previous);
      toast.error("The change was not saved", { description: error.message });
    },
    onSuccess: setJob,
  });
  return { patch, setJob };
}

function Step({
  index,
  done,
  title,
  description,
  onToggle,
  children,
}: {
  index: number;
  done: boolean;
  title: string;
  description?: React.ReactNode;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <li className="relative flex gap-4 pb-6 last:pb-0">
      <span aria-hidden className="absolute left-[15px] top-9 h-[calc(100%-2.25rem)] w-px bg-border last:hidden" />
      <button
        type="button"
        onClick={onToggle}
        className="relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full bg-background"
        aria-label={done ? `Mark step ${index}, ${title}, as not done` : `Mark step ${index}, ${title}, as done`}
        aria-pressed={done}
      >
        {done ? <CheckCircle2 className="size-7 text-success" /> : <Circle className="size-7 text-muted-foreground" />}
      </button>
      <div className="min-w-0 flex-1 space-y-3 pt-1">
        <div>
          <h3 className={cn("text-section", done && "text-muted-foreground")}>
            {index}. {title}
          </h3>
          {description && <p className="max-w-prose text-body text-muted-foreground">{description}</p>}
        </div>
        {children}
      </div>
    </li>
  );
}

function CvEditor({ job, onDone }: { job: JobDetail; onDone: (job: JobDetail) => void }) {
  const [content, setContent] = React.useState<TailoredContent | null>(null);
  const draft = useMutation({
    mutationFn: () => api.post<TailoredContent>(`/api/jobs/${job.id}/tailor/preview`),
    onSuccess: setContent,
    onError: (error: Error) => toast.error("Groq could not draft the CV", { description: error.message }),
  });
  const build = useMutation({
    mutationFn: () => api.post<{ path: string; job: JobDetail }>(`/api/jobs/${job.id}/tailor`, content),
    onSuccess: (result) => {
      toast.success("Tailored CV created from your edits");
      setContent(null);
      onDone(result.job);
    },
    onError: (error: Error) => toast.error("The CV was not built", { description: error.message }),
  });

  if (!content) {
    return (
      <Button variant="outline" size="sm" onClick={() => draft.mutate()} loading={draft.isPending}>
        <Pencil /> {draft.isPending ? "Asking Groq (about 10 seconds)…" : "Edit summary & bullets before generating"}
      </Button>
    );
  }
  return (
    <Card className="space-y-4 p-4">
      <p className="text-caption text-muted-foreground">
        Groq drafted this from your resume. Edit anything, then build the Word file. Only facts from your resume are used.
      </p>
      <Field label="Professional summary" htmlFor="cv-summary">
        <Textarea id="cv-summary" rows={4} value={content.summary} onChange={(e) => setContent({ ...content, summary: e.target.value })} />
      </Field>
      <Field label="Role-matched highlights">
        <StringListEditor
          value={content.bullets}
          onChange={(bullets) => setContent({ ...content, bullets })}
          itemLabel="Highlight"
          addLabel="Add highlight"
        />
      </Field>
      <div className="flex gap-2">
        <Button onClick={() => build.mutate()} loading={build.isPending} disabled={!content.summary.trim()}>
          <FileText /> Build CV
        </Button>
        <Button variant="ghost" onClick={() => setContent(null)}>
          Cancel
        </Button>
      </div>
    </Card>
  );
}

export function ApplyWorkspace({ job }: { job: JobDetail }) {
  const confirm = useConfirm();
  const { patch, setJob } = useJobMutations(job);
  const [preview, setPreview] = React.useState<DocumentItem | null>(null);
  const [company, setCompany] = React.useState(job.company.startsWith("Partner (") ? "" : job.company);
  const [notes, setNotes] = React.useState(job.notes);
  React.useEffect(() => setNotes(job.notes), [job.notes]);
  const resume = useQuery({ queryKey: keys.resume, queryFn: () => api.get<ResumeResponse>("/api/resume") });
  const checklist = job.apply_checklist ?? {};
  const mark = (key: StepKey, value = true) => {
    if (Boolean(checklist[key]) !== value) patch.mutate({ apply_checklist: { ...checklist, [key]: value } });
  };
  const toggle = (key: StepKey) => () => mark(key, !checklist[key]);

  const cvDoc = job.documents.find((d) => d.kind === "cv" && d.exists && d.path === job.cv_path) ?? job.documents.find((d) => d.kind === "cv" && d.exists);
  const letterDoc = job.documents.find((d) => d.kind === "cover_letter" && d.exists);

  const tailor = useMutation({
    mutationFn: () => api.post<{ path: string; job: JobDetail }>(`/api/jobs/${job.id}/tailor`),
    onSuccess: (result) => {
      toast.success(cvDoc ? "CV regenerated" : "Tailored CV created");
      setJob(result.job);
    },
    onError: (error: Error) => toast.error("Tailoring failed", { description: error.message }),
  });
  const letter = useMutation({
    mutationFn: () => api.post<{ path: string; job: JobDetail }>(`/api/jobs/${job.id}/cover-letter`, { company: company || null }),
    onSuccess: (result) => {
      toast.success("Cover letter created");
      setJob(result.job);
    },
    onError: (error: Error) => toast.error("The cover letter was not created", { description: error.message }),
  });
  const autofill = useMutation({
    mutationFn: () => api.post<{ ok: boolean; filled: string[]; error?: string }>(`/api/jobs/${job.id}/autofill`),
    onSuccess: (result) => {
      if (result.ok) {
        toast.success(result.filled.length ? `Filled: ${result.filled.join(", ")}` : "The page opened, but no form fields were recognised", {
          description: "Review everything in the browser window and submit it yourself.",
        });
      } else {
        toast.warning("Auto-fill stopped early", { description: result.error });
      }
    },
    onError: (error: Error) => toast.error("Auto-fill could not start", { description: error.message }),
  });

  const info = resume.data?.data.personal_info;
  const answers: [string, string][] = [
    ["Full name", info?.full_name ?? ""],
    ["Email", info?.email ?? ""],
    ["Phone", info?.phone ?? ""],
    ["Location", info?.location ?? ""],
    ...Object.entries(resume.data?.data.standard_answers ?? {}).map(([k, v]) => [humanize(k), v] as [string, string]),
  ];

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <ol aria-label="Apply checklist">
        <Step
          index={1}
          done={Boolean(checklist.review)}
          onToggle={toggle("review")}
          title="Review the posting"
          description={job.role_family ? <>Matched role family: <strong>{job.role_family}</strong></> : "No role family matched this title."}
        >
          <div className="flex flex-wrap gap-2">
            {job.url && (
              <a className={buttonVariants({ size: "sm" })} href={job.url} target="_blank" rel="noopener noreferrer" onClick={() => mark("review")}>
                <ExternalLink /> Open posting
              </a>
            )}
          </div>
          {job.matched_keywords.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-caption text-muted-foreground">Your skills this posting mentions</p>
              <div className="flex flex-wrap gap-1.5">
                {job.matched_keywords.map((k) => (
                  <Badge key={k} variant="success">{k}</Badge>
                ))}
              </div>
            </div>
          )}
          {job.missing_keywords.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-caption text-muted-foreground">Role keywords it does not mention</p>
              <div className="flex flex-wrap gap-1.5">
                {job.missing_keywords.map((k) => (
                  <Badge key={k} variant="outline">{k}</Badge>
                ))}
              </div>
            </div>
          )}
        </Step>

        <Step index={2} done={Boolean(checklist.cv)} onToggle={toggle("cv")} title="Your tailored CV"
          description={cvDoc ? <>Created <RelativeTime value={cvDoc.created_at} />.</> : "No CV yet for this job."}>
          <div className="flex flex-wrap gap-2">
            {cvDoc ? (
              <>
                <Button size="sm" variant="outline" onClick={() => setPreview(cvDoc)}>
                  <Eye /> Preview
                </Button>
                <a className={buttonVariants({ size: "sm", variant: "outline" })} href={`/api/documents/${cvDoc.id}/download`} onClick={() => mark("cv")}>
                  <Download /> Download
                </a>
              </>
            ) : null}
            <Button size="sm" variant={cvDoc ? "ghost" : "default"} onClick={() => tailor.mutate()} loading={tailor.isPending}>
              <RefreshCw /> {cvDoc ? "Regenerate" : "Generate CV"}
            </Button>
          </div>
          <CvEditor job={job} onDone={setJob} />
        </Step>

        <Step index={3} done={Boolean(checklist.cover_letter)} onToggle={toggle("cover_letter")} title="Cover letter"
          description="Built from the letter text for this role family, addressed to the company.">
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Company name on the letter" htmlFor="letter-company" className="w-64"
              description={job.company.startsWith("Partner (") ? "The alert did not include it. Check the posting." : undefined}>
              <Input id="letter-company" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Company name" />
            </Field>
            <Button size="sm" variant={letterDoc ? "ghost" : "default"} onClick={() => letter.mutate()} loading={letter.isPending}>
              <RefreshCw /> {letterDoc ? "Regenerate" : "Generate cover letter"}
            </Button>
            {letterDoc && (
              <>
                <Button size="sm" variant="outline" onClick={() => setPreview(letterDoc)}>
                  <Eye /> Preview
                </Button>
                <a className={buttonVariants({ size: "sm", variant: "outline" })} href={`/api/documents/${letterDoc.id}/download`} onClick={() => mark("cover_letter")}>
                  <Download /> Download
                </a>
              </>
            )}
          </div>
        </Step>

        <Step index={4} done={Boolean(checklist.answers)} onToggle={toggle("answers")} title="Copy-ready answers"
          description="Edit these under Profile → Standard answers.">
          <dl className="grid gap-2 sm:grid-cols-2">
            {answers.map(([label, value]) => (
              <div key={label} className="flex items-center gap-2 rounded-md border p-2">
                <div className="min-w-0 flex-1">
                  <dt className="text-caption text-muted-foreground">{label}</dt>
                  <dd className="truncate" title={value}>{value || <span className="text-muted-foreground">Not set</span>}</dd>
                </div>
                <CopyButton value={value} label={label} />
              </div>
            ))}
          </dl>
        </Step>

        <Step index={5} done={Boolean(checklist.apply)} onToggle={toggle("apply")} title="Apply"
          description="You always review and press submit yourself.">
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              loading={autofill.isPending}
              disabled={!job.url}
              onClick={async () => {
                const ok = await confirm({
                  title: "Open the posting with auto-fill?",
                  description: (
                    <>
                      <p>A visible browser window opens, fills your name, email and phone, and attaches the tailored CV where it can.</p>
                      <p className="mt-2 font-medium">Nothing is submitted. Check every field, submit it yourself, then close the window.</p>
                    </>
                  ),
                  confirmLabel: "Open browser",
                });
                if (ok) autofill.mutate();
              }}
            >
              <Bot /> Auto-fill with browser
            </Button>
            <Button
              size="sm"
              onClick={() => {
                patch.mutate({ application_status: "applied", apply_checklist: { ...checklist, apply: true } });
                toast.success("Marked as applied", { description: "Set a follow-up date below." });
              }}
              disabled={job.application_status !== "not_applied"}
            >
              <Send /> I applied manually
            </Button>
          </div>
          {autofill.data && (
            <p className={cn("text-body", autofill.data.ok ? "text-success" : "text-warning")} role="status">
              {autofill.data.ok
                ? `Auto-fill finished. Filled: ${autofill.data.filled.join(", ") || "nothing recognised"}.`
                : `Auto-fill stopped: ${autofill.data.error}`}
            </p>
          )}
        </Step>

        <Step index={6} done={Boolean(checklist.track)} onToggle={toggle("track")} title="Track">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Application status" htmlFor="app-status">
              <Select
                id="app-status"
                value={job.application_status}
                onValueChange={(application_status) => patch.mutate({ application_status: application_status as JobDetail["application_status"] })}
                options={APPLICATION_STATUS_OPTIONS}
              />
            </Field>
            <Field label="Applied on" htmlFor="applied-at">
              <Input id="applied-at" type="date" value={job.applied_at?.slice(0, 10) ?? ""} onChange={(e) => patch.mutate({ applied_at: e.target.value })} />
            </Field>
            <Field label="Follow up on" htmlFor="follow-up">
              <Input id="follow-up" type="date" value={job.follow_up_at?.slice(0, 10) ?? ""} onChange={(e) => patch.mutate({ follow_up_at: e.target.value })} />
            </Field>
          </div>
          <Field label="Notes" htmlFor="job-notes">
            <Textarea
              id="job-notes"
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => {
                if (notes !== job.notes) {
                  patch.mutate({ notes });
                  toast.success("Notes saved");
                }
              }}
              placeholder="Recruiter name, interview dates, what you sent…"
            />
          </Field>
        </Step>
      </ol>
      <aside className="space-y-4">
        {job.tips.length > 0 && (
          <Card className="space-y-2 p-4">
            <h3 className="flex items-center gap-2 text-section">
              <Lightbulb className="size-4 text-warning" /> Tips for this source
            </h3>
            <ul className="list-disc space-y-1.5 pl-4 text-body text-muted-foreground">
              {job.tips.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          </Card>
        )}
        <Card className="p-4 text-body">
          <p className="font-medium">Progress</p>
          <p className="tabular text-muted-foreground">
            {Object.values(checklist).filter(Boolean).length} of 6 steps done
          </p>
        </Card>
      </aside>
      <DocumentPreviewDialog document={preview} onOpenChange={(open) => !open && setPreview(null)} />
    </div>
  );
}
