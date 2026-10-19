import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Briefcase, Check, Play } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useStartRun } from "@/components/layout/RunControl";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import { ImportFlow, type ImportSource } from "@/features/onboarding/ImportFlow";
import { GmailCard, useGmailRedirectToast } from "@/features/settings/GmailCard";
import { SecretsPanel } from "@/features/settings/SecretsPanel";
import { TargetRolesQuick } from "@/features/settings/TargetRolesQuick";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { ResumeResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS = ["Choose a source", "Review", "Connect & configure"];

function markDone() {
  try {
    localStorage.setItem("onboarding-dismissed", "1");
  } catch {
    /* ignore */
  }
}

function Stepper({ current }: { current: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-2" aria-label="Onboarding steps">
      {STEPS.map((label, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li key={label} className="flex items-center gap-2" aria-current={active ? "step" : undefined}>
            <span
              className={cn(
                "flex size-7 items-center justify-center rounded-full border text-caption font-semibold tabular",
                done && "border-success bg-success text-success-foreground",
                active && "border-primary bg-primary text-primary-foreground",
              )}
            >
              {done ? <Check className="size-4" /> : index + 1}
            </span>
            <span className={cn("text-body", active ? "font-medium" : "text-muted-foreground")}>{label}</span>
            {index < STEPS.length - 1 && <span aria-hidden className="mx-1 h-px w-8 bg-border" />}
          </li>
        );
      })}
    </ol>
  );
}

export default function OnboardingPage() {
  const navigate = useNavigate();
  const startRun = useStartRun();
  const [params] = useSearchParams();
  const only = (params.get("source") as ImportSource | null) ?? undefined;
  const returnTo = params.get("return");
  const importOnly = Boolean(returnTo);
  const resume = useQuery({ queryKey: keys.resume, queryFn: () => api.get<ResumeResponse>("/api/resume") });
  const [stage, setStage] = React.useState<"source" | "edit" | "merge">("source");
  const [step, setStep] = React.useState(params.get("step") === "connect" ? 2 : 0);
  const [applied, setApplied] = React.useState(false);
  const [flowKey, setFlowKey] = React.useState(0);
  useGmailRedirectToast();

  const current = step === 2 ? 2 : stage === "source" && !applied ? 0 : 1;
  const finish = () => {
    markDone();
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="border-b bg-background">
        <div className="mx-auto flex max-w-content flex-wrap items-center gap-4 px-4 py-3 md:px-8">
          <Link to="/" onClick={markDone} className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Briefcase className="size-4" />
            </span>
            <span className="text-section">Job Agent</span>
          </Link>
          {!importOnly && <Stepper current={current} />}
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            {importOnly ? (
              <Link to={returnTo!} className={buttonVariants({ variant: "ghost" })}>
                <ArrowLeft /> Back
              </Link>
            ) : (
              <Button variant="ghost" onClick={finish}>
                Skip setup
              </Button>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-content px-4 py-8 md:px-8">
        {step < 2 ? (
          <>
            <div className="mb-6 max-w-prose space-y-1">
              <h1 className="text-title">
                {importOnly ? (only === "linkedin" ? "Import from LinkedIn" : "Import a resume file") : "Set up your profile"}
              </h1>
              <p className="text-body text-muted-foreground">
                {stage === "merge"
                  ? "Decide what to keep. Nothing is saved until you click Apply, and a backup is made first."
                  : stage === "edit"
                    ? "Compare the extracted fields with your original and correct anything that is off."
                    : "Your master resume is the single source of truth for every tailored CV. Sources can be combined: start with a PDF, then fill gaps from LinkedIn."}
              </p>
            </div>
            {applied && stage === "source" ? (
              <Card className="max-w-2xl space-y-4 p-6">
                <h2 className="text-section">Your profile was updated</h2>
                <p className="text-body text-muted-foreground">
                  {resume.data ? `It now has ${resume.data.data.experience.length} experience entries and ${resume.data.data.projects.length} projects.` : ""}{" "}
                  Import another source to fill gaps, or continue.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" onClick={() => { setApplied(false); setFlowKey((k) => k + 1); }}>
                    Import another source
                  </Button>
                  {importOnly ? (
                    <Button onClick={() => navigate(returnTo!)}>Back to {returnTo === "/profile" ? "profile" : "settings"} <ArrowRight /></Button>
                  ) : (
                    <Button onClick={() => setStep(2)}>Continue <ArrowRight /></Button>
                  )}
                </div>
              </Card>
            ) : (
              <ImportFlow
                key={flowKey}
                only={only}
                onStageChange={setStage}
                onUseExisting={
                  importOnly
                    ? undefined
                    : () => {
                        if (resume.data?.empty) {
                          toast.error("resume_data.yaml is empty", { description: "Upload a resume or a LinkedIn export instead." });
                          return;
                        }
                        setStep(2);
                      }
                }
                onApplied={() => {
                  setApplied(true);
                  resume.refetch();
                }}
              />
            )}
          </>
        ) : (
          <div className="max-w-3xl space-y-6">
            <div className="space-y-1">
              <h1 className="text-title">Connect & configure</h1>
              <p className="max-w-prose text-body text-muted-foreground">
                Add your API keys and test them, connect Gmail for job-alert emails, and pick the roles to search for.
                Everything here can be skipped and changed later in Settings.
              </p>
            </div>
            <SecretsPanel groups={["groq", "adzuna"]} />
            <GmailCard showSenders={false} returnTo="/onboarding?step=connect" />
            <TargetRolesQuick />
            <Card className="flex flex-wrap items-center gap-3 p-4">
              <p className="flex-1 text-body">You're set. The first run takes a few minutes.</p>
              <Button variant="outline" onClick={finish}>
                Go to dashboard
              </Button>
              <Button
                onClick={() => {
                  markDone();
                  navigate("/");
                  startRun();
                }}
              >
                <Play /> Run your first search
              </Button>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}
