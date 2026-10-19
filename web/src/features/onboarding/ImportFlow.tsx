import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, FileText, FileUp, Linkedin, Loader2 } from "lucide-react";
import * as React from "react";
import { FormProvider, useForm } from "react-hook-form";
import { toast } from "sonner";
import { Dropzone } from "@/components/dropzone";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/controls";
import { Card } from "@/components/ui/primitives";
import { MergeReview } from "@/features/onboarding/MergeReview";
import { fromForm, profileSchema, toForm, type ProfileForm } from "@/features/profile/schema";
import {
  CertificationsSection,
  EducationSection,
  ExperienceSection,
  LanguagesSection,
  PersonalInfoSection,
  ProjectsSection,
} from "@/features/profile/sections";
import { api } from "@/lib/api";
import type { ImportResult } from "@/lib/types";

export type ImportSource = "file" | "linkedin";

function LinkedInHowTo() {
  return (
    <details className="rounded-md bg-muted/60 p-3 text-body">
      <summary className="cursor-pointer font-medium">How to get your LinkedIn export</summary>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
        <li>
          On LinkedIn open <strong>Settings → Data privacy → Get a copy of your data</strong> (
          <a
            className="text-primary underline underline-offset-4 hover:decoration-2"
            href="https://www.linkedin.com/mypreferences/d/download-my-data"
            target="_blank"
            rel="noopener noreferrer"
          >
            open it directly
          </a>
          ).
        </li>
        <li>
          Choose <strong>“Want something in particular?”</strong> and tick Profile, Positions, Education,
          Skills, Certifications, Languages and Projects. That is enough.
        </li>
        <li>
          Click <strong>Request archive</strong>. LinkedIn emails a download link, usually within 10 minutes
          and at most a day.
        </li>
        <li>
          Download the .zip and drop it here. Only the profile files are read; messages and connections are
          ignored.
        </li>
      </ol>
    </details>
  );
}

export function SourcePicker({
  onResult,
  onUseExisting,
  only,
}: {
  onResult: (result: ImportResult, file: File) => void;
  onUseExisting?: () => void;
  only?: ImportSource;
}) {
  const [enhance, setEnhance] = React.useState(false);
  const upload = useMutation({
    mutationFn: ({ file, source }: { file: File; source: ImportSource }) =>
      source === "linkedin"
        ? api.upload<ImportResult>("/api/resume/import/linkedin", file, { enhance: String(enhance) })
        : api.upload<ImportResult>("/api/resume/import", file),
    onSuccess: (result, { file }) => onResult(result, file),
    onError: (error: Error) => toast.error("The import did not work", { description: error.message }),
  });
  const busy = upload.isPending;
  const source = upload.variables?.source;

  const cards = [
    {
      id: "file" as const,
      icon: FileUp,
      title: "Upload resume",
      text: "A PDF or Word file. Groq reads it into your profile; you review every field before anything is saved.",
      body: (
        <Dropzone
          accept=".pdf,.docx"
          label="Drop your resume here or click to browse"
          hint="PDF or DOCX, up to 50 MB"
          disabled={busy}
          onFile={(file) => upload.mutate({ file, source: "file" })}
        />
      ),
    },
    {
      id: "linkedin" as const,
      icon: Linkedin,
      title: "Import from LinkedIn",
      text: "Your LinkedIn data export (.zip). Works without an API key.",
      body: (
        <div className="space-y-3">
          <Dropzone
            accept=".zip"
            label="Drop the LinkedIn .zip here or click to browse"
            hint="The archive LinkedIn emailed you"
            disabled={busy}
            onFile={(file) => upload.mutate({ file, source: "linkedin" })}
          />
          <label className="flex items-center gap-2 text-body">
            <Switch checked={enhance} onCheckedChange={setEnhance} /> Enhance with AI
            <span className="text-caption text-muted-foreground">
              (bullets, skill categories, tech stacks)
            </span>
          </label>
          <LinkedInHowTo />
        </div>
      ),
    },
  ].filter((card) => !only || card.id === only);

  return (
    <div className="space-y-4">
      <div className={`grid gap-4 ${only ? "" : onUseExisting ? "lg:grid-cols-3" : "lg:grid-cols-2"}`}>
        {cards.map(({ id, icon: Icon, title, text, body }) => (
          <Card key={id} className="flex flex-col gap-3 p-4">
            <h3 className="flex items-center gap-2 text-section">
              <Icon className="size-5 text-primary" /> {title}
            </h3>
            <p className="text-body text-muted-foreground">{text}</p>
            {body}
          </Card>
        ))}
        {onUseExisting && !only && (
          <Card className="flex flex-col gap-3 p-4">
            <h3 className="flex items-center gap-2 text-section">
              <FileText className="size-5 text-primary" /> Use existing resume_data.yaml
            </h3>
            <p className="flex-1 text-body text-muted-foreground">
              Keep the profile that is already in resume_data.yaml. You can edit it any time under Profile.
            </p>
            <Button variant="outline" onClick={onUseExisting}>
              Use my existing file <ArrowRight />
            </Button>
          </Card>
        )}
      </div>
      {busy && (
        <p className="flex items-center gap-2 text-body text-muted-foreground" role="status">
          <Loader2 className="size-4 animate-spin" />
          {source === "file"
            ? "Reading your resume with Groq. This takes 10–30 seconds…"
            : "Reading your LinkedIn export…"}
        </p>
      )}
    </div>
  );
}

function FileReview({
  result,
  file,
  onContinue,
  onBack,
}: {
  result: ImportResult;
  file: File;
  onContinue: (next: ImportResult) => void;
  onBack: () => void;
}) {
  const form = useForm<ProfileForm>({
    resolver: zodResolver(profileSchema),
    mode: "onChange",
    defaultValues: toForm(result.draft),
  });
  const pdfUrl = React.useMemo(
    () => (file.name.toLowerCase().endsWith(".pdf") ? URL.createObjectURL(file) : null),
    [file],
  );
  React.useEffect(
    () => () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    },
    [pdfUrl],
  );

  const review = useMutation({
    mutationFn: (data: ProfileForm) =>
      api.post<ImportResult>("/api/resume/import/review", {
        source: "resume_file",
        draft: fromForm(data),
        skills_pool: result.skills_pool,
        skill_suggestions: result.skill_suggestions,
        warnings: result.warnings,
        low_confidence: result.low_confidence,
      }),
    onSuccess: onContinue,
    onError: (error: Error) => toast.error("Check the highlighted fields", { description: error.message }),
  });

  const lowConfidence = result.low_confidence.map((path) =>
    path
      .replace(":", " ")
      .replace(/\b(\d+)\b/, (n) => `#${Number(n) + 1}`)
      .replace(/_/g, " "),
  );

  return (
    <FormProvider {...form}>
      <div className="grid gap-6 pb-24 xl:grid-cols-2">
        <Card className="sticky top-20 hidden h-[calc(100vh-7rem)] overflow-hidden xl:block">
          {pdfUrl ? (
            <iframe title="Original resume" src={pdfUrl} className="size-full" />
          ) : result.preview_html ? (
            <div className="h-full overflow-y-auto bg-muted/40 p-4">
              <div
                className="doc-preview rounded-md bg-card p-6 shadow-card"
                dangerouslySetInnerHTML={{ __html: result.preview_html }}
              />
            </div>
          ) : (
            <p className="p-4 text-body text-muted-foreground">No preview available for this file.</p>
          )}
        </Card>
        <form
          className="min-w-0 space-y-6"
          onSubmit={form.handleSubmit((data) => review.mutate(data))}
          noValidate
        >
          {lowConfidence.length > 0 && (
            <div className="rounded-lg border border-warning/30 bg-warning-soft p-4 text-body" role="status">
              <p className="flex items-center gap-2 font-medium text-warning">
                <AlertTriangle className="size-4" /> Check these fields against the original
              </p>
              <p className="mt-1 text-foreground/80">{lowConfidence.join(", ")}</p>
            </div>
          )}
          <PersonalInfoSection />
          <ExperienceSection />
          <ProjectsSection />
          <EducationSection />
          <CertificationsSection />
          <LanguagesSection />
          <div className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 shadow-overlay backdrop-blur">
            <div className="mx-auto flex max-w-content items-center justify-end gap-2 px-4 py-3 md:px-8">
              <Button type="button" variant="ghost" onClick={onBack}>
                Choose another file
              </Button>
              <Button type="submit" loading={review.isPending}>
                Continue to review <ArrowRight />
              </Button>
            </div>
          </div>
        </form>
      </div>
    </FormProvider>
  );
}

/** Upload -> (file: edit) -> merge review -> applied. Used by onboarding and Profile → Import. */
export function ImportFlow({
  only,
  onUseExisting,
  onApplied,
  onStageChange,
}: {
  only?: ImportSource;
  onUseExisting?: () => void;
  onApplied: () => void;
  onStageChange?: (stage: "source" | "edit" | "merge") => void;
}) {
  const [state, setState] = React.useState<{ result: ImportResult; file: File; editing: boolean } | null>(
    null,
  );
  React.useEffect(() => {
    onStageChange?.(!state ? "source" : state.editing ? "edit" : "merge");
  }, [state, onStageChange]);

  if (!state) {
    return (
      <SourcePicker
        only={only}
        onUseExisting={onUseExisting}
        onResult={(result, file) => setState({ result, file, editing: result.source === "resume_file" })}
      />
    );
  }
  if (state.editing) {
    return (
      <FileReview
        result={state.result}
        file={state.file}
        onBack={() => setState(null)}
        onContinue={(next) => setState({ ...state, result: next, editing: false })}
      />
    );
  }
  return (
    <MergeReview
      result={state.result}
      onBack={() => setState(state.result.source === "resume_file" ? { ...state, editing: true } : null)}
      onApplied={() => {
        setState(null);
        onApplied();
      }}
    />
  );
}
