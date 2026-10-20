import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Code2,
  Download,
  Eye,
  FileUp,
  History,
  Linkedin,
  RotateCcw,
  Save,
  Sparkles,
  UserRound,
} from "lucide-react";
import * as React from "react";
import { FormProvider, useForm, useWatch, type FieldPath } from "react-hook-form";
import { Link, useBlocker, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/common";
import { useConfirm } from "@/components/confirm";
import { EmptyState, ErrorState, SkeletonForm } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { CvPreviewPanel } from "@/features/profile/CvPreviewPanel";
import { HistoryDrawer } from "@/features/profile/HistoryDrawer";
import {
  SECTIONS,
  countChanges,
  fromForm,
  profileSchema,
  toForm,
  type ProfileForm,
} from "@/features/profile/schema";
import {
  CertificationsSection,
  EducationSection,
  ExperienceSection,
  LanguagesSection,
  PersonalInfoSection,
  ProjectsSection,
  RoleProfilesSection,
  SkillsSection,
  StandardAnswersSection,
} from "@/features/profile/sections";
import { ApiError, api } from "@/lib/api";

const YamlEditor = React.lazy(() =>
  import("@/features/profile/YamlEditor").then((m) => ({ default: m.YamlEditor })),
);
import { keys } from "@/lib/queries";
import type { ResumeResponse, SettingsResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Map server field paths (role_profiles.<name>.focus) onto the form's array paths. */
function toFormPath(loc: string[], form: ProfileForm): string | null {
  const [section, key, ...rest] = loc;
  const byName = (items: { name?: string; key?: string }[], field: "name" | "key") =>
    items.findIndex((item) => item[field] === key);
  if (section === "role_profiles")
    return `role_profiles.${byName(form.role_profiles, "name")}.${rest.join(".") || "name"}`;
  if (section === "core_skills") return `core_skills.${byName(form.core_skills, "name")}.skills`;
  if (section === "standard_answers") return `standard_answers.${byName(form.standard_answers, "key")}.value`;
  if (section === "languages") return `languages.${key}.value`;
  return loc.join(".");
}

export default function ProfilePage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [params, setParams] = useSearchParams();
  const [yamlMode, setYamlMode] = React.useState(false);
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [activeSection, setActiveSection] = React.useState<string>(SECTIONS[0].id);

  const resume = useQuery({ queryKey: keys.resume, queryFn: () => api.get<ResumeResponse>("/api/resume") });
  const settings = useQuery({
    queryKey: keys.settings,
    queryFn: () => api.get<SettingsResponse>("/api/settings/search"),
  });
  const targetRoles = Object.keys(settings.data?.settings.target_roles ?? {});

  const form = useForm<ProfileForm>({
    resolver: zodResolver(profileSchema),
    mode: "onChange",
    defaultValues: resume.data ? toForm(resume.data.data) : undefined,
  });
  const { formState, reset, handleSubmit, setError, control } = form;

  const loaded = React.useRef<string | null>(null);
  const [ready, setReady] = React.useState(false);
  React.useEffect(() => {
    if (resume.data && loaded.current !== resume.data.etag && !formState.isDirty) {
      loaded.current = resume.data.etag;
      reset(toForm(resume.data.data));
      setReady(true);
    }
  }, [resume.data, reset, formState.isDirty]);

  const values = useWatch({ control }) as ProfileForm;
  const changeCount = React.useMemo(
    () => (formState.isDirty && formState.defaultValues ? countChanges(formState.defaultValues, values) : 0),
    [formState.isDirty, formState.defaultValues, values],
  );
  const dirty = changeCount > 0;
  const errorCount = Object.keys(formState.errors).length;

  const save = useMutation({
    mutationFn: (data: ProfileForm) =>
      api.put<ResumeResponse & { backup_id: string | null }>("/api/resume", {
        data: fromForm(data),
        etag: resume.data?.etag,
      }),
    onSuccess: (result) => {
      loaded.current = result.etag;
      queryClient.setQueryData(keys.resume, result);
      queryClient.invalidateQueries({ queryKey: keys.backups });
      reset(toForm(result.data));
      toast.success("Profile saved", {
        description: result.warnings.length
          ? `${result.warnings.length} reference warning(s) — see the top of the page.`
          : "A backup of the previous version is in History.",
      });
    },
    onError: (error: Error, data) => {
      if (error instanceof ApiError && error.status === 422) {
        const errors = (error.detail as { errors?: { loc: string[]; msg: string }[] })?.errors ?? [];
        errors.forEach((item) => {
          const path = toFormPath(item.loc, data);
          if (path) setError(path as FieldPath<ProfileForm>, { message: item.msg });
        });
        toast.error("Some fields need fixing", {
          description: errors
            .slice(0, 2)
            .map((e) => e.msg)
            .join(" "),
        });
      } else if (error instanceof ApiError && error.status === 409) {
        toast.error("The resume changed on disk", {
          description:
            "It was edited outside this page. Reload to get the latest version (your edits will be lost).",
          action: { label: "Reload", onClick: () => discard(true) },
        });
      } else {
        toast.error("The profile was not saved", { description: error.message });
      }
    },
  });

  const onSubmit = handleSubmit(
    (data) => save.mutate(data),
    () => toast.error("Fix the highlighted fields before saving."),
  );

  const discard = React.useCallback(
    (refetch = false) => {
      if (refetch) {
        loaded.current = null;
        reset(undefined, { keepValues: false });
        resume.refetch().then((r) => r.data && reset(toForm(r.data.data)));
      } else if (resume.data) reset(toForm(resume.data.data));
    },
    [reset, resume],
  );

  // Unsaved-changes guard for in-app navigation and tab close.
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname,
  );
  React.useEffect(() => {
    if (blocker.state !== "blocked") return;
    confirm({
      title: "Leave without saving?",
      description: `You have ${changeCount} unsaved change(s) on your profile.`,
      confirmLabel: "Leave and discard",
      destructive: true,
    }).then((ok) => (ok ? blocker.proceed() : blocker.reset()));
  }, [blocker, confirm, changeCount]);
  React.useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  // Ctrl+S saves.
  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s" && !yamlMode) {
        event.preventDefault();
        if (dirty) onSubmit();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [dirty, onSubmit, yamlMode]);

  // Highlight the section in view.
  React.useEffect(() => {
    if (yamlMode) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveSection(visible[0].target.id);
      },
      { rootMargin: "-80px 0px -60% 0px" },
    );
    SECTIONS.forEach((section) => {
      const element = document.getElementById(section.id);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, [yamlMode, resume.data]);

  const addExperience = params.get("add") === "experience";
  React.useEffect(() => {
    if (addExperience && resume.data) {
      window.setTimeout(
        () => document.getElementById("experience")?.scrollIntoView({ behavior: "smooth" }),
        100,
      );
      const next = new URLSearchParams(params);
      next.delete("add");
      setParams(next, { replace: true });
    }
  }, [addExperience, resume.data, params, setParams]);

  const openYaml = async () => {
    if (dirty) {
      const ok = await confirm({
        title: "Switch to the YAML editor?",
        description: "Unsaved form changes will be discarded. Save first if you want to keep them.",
        confirmLabel: "Discard and switch",
        destructive: true,
      });
      if (!ok) return;
      discard();
    }
    setYamlMode(true);
  };

  const header = (
    <PageHeader
      title="Profile"
      description="Your master resume. Every tailored CV and cover letter is built from these facts."
      actions={
        <>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <Download /> Import
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => navigate("/onboarding?source=file&return=/profile")}>
                <FileUp /> From resume file…
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => navigate("/onboarding?source=linkedin&return=/profile")}>
                <Linkedin /> From LinkedIn export…
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="outline" onClick={() => setHistoryOpen(true)}>
            <History /> History
          </Button>
          {!yamlMode && (
            <Button
              variant={previewOpen ? "secondary" : "outline"}
              onClick={() => setPreviewOpen((o) => !o)}
              aria-pressed={previewOpen}
            >
              <Eye /> Preview CV
            </Button>
          )}
          <Button
            variant={yamlMode ? "secondary" : "ghost"}
            onClick={() => (yamlMode ? setYamlMode(false) : openYaml())}
            aria-pressed={yamlMode}
          >
            <Code2 /> Advanced: Edit YAML
          </Button>
        </>
      }
    />
  );

  if (resume.isPending || (resume.data && !ready)) {
    return (
      <>
        {header}
        <SkeletonForm fields={8} />
      </>
    );
  }
  if (resume.isError) {
    const yamlBroken = resume.error instanceof ApiError && resume.error.status === 422;
    return (
      <>
        {header}
        {yamlMode ? (
          <React.Suspense fallback={<SkeletonForm fields={10} />}>
            <YamlEditor onClose={() => setYamlMode(false)} />
          </React.Suspense>
        ) : (
          <ErrorState
            title={yamlBroken ? "Your profile YAML has problems" : "Your profile could not be loaded"}
            error={resume.error}
            onRetry={yamlBroken ? () => setYamlMode(true) : () => resume.refetch()}
          />
        )}
      </>
    );
  }

  const warnings = resume.data.warnings;
  return (
    <FormProvider {...form}>
      {header}
      <HistoryDrawer open={historyOpen} onOpenChange={setHistoryOpen} dirty={dirty} />
      {yamlMode ? (
        <React.Suspense fallback={<SkeletonForm fields={10} />}>
          <YamlEditor onClose={() => setYamlMode(false)} />
        </React.Suspense>
      ) : (
        <>
          {resume.data.empty && (
            <EmptyState
              className="mb-6"
              icon={UserRound}
              title="Your profile is empty"
              description="Import your resume or LinkedIn data to fill it in a minute, or type it in below."
              action={
                <Link to="/onboarding" className={buttonVariants()}>
                  <Sparkles /> Start onboarding
                </Link>
              }
            />
          )}
          {warnings.length > 0 && (
            <div
              className="mb-6 rounded-lg border border-warning/30 bg-warning-soft p-4 text-body"
              role="status"
            >
              <p className="mb-1 font-medium text-warning">Check these references</p>
              <ul className="list-disc space-y-0.5 pl-5 text-foreground/80">
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
          <div
            className={cn(
              "grid gap-6",
              previewOpen ? "xl:grid-cols-[11rem_minmax(0,1fr)_26rem]" : "lg:grid-cols-[11rem_minmax(0,1fr)]",
            )}
          >
            <nav aria-label="Profile sections" className="hidden lg:block">
              <ul className="sticky top-20 space-y-0.5">
                {SECTIONS.map((section) => {
                  const hasError = Boolean(formState.errors[section.field as keyof ProfileForm]);
                  return (
                    <li key={section.id}>
                      <a
                        href={`#${section.id}`}
                        className={cn(
                          "flex items-center justify-between rounded-md px-3 py-1.5 text-body text-muted-foreground hover:bg-muted hover:text-foreground",
                          activeSection === section.id && "bg-muted font-medium text-foreground",
                        )}
                        aria-current={activeSection === section.id ? "location" : undefined}
                      >
                        {section.label}
                        {hasError && (
                          <span className="size-2 rounded-full bg-danger" aria-label="has errors" />
                        )}
                      </a>
                    </li>
                  );
                })}
              </ul>
            </nav>
            <form onSubmit={onSubmit} className="min-w-0 space-y-6 pb-24" noValidate>
              <PersonalInfoSection />
              <RoleProfilesSection targetRoles={targetRoles} />
              <SkillsSection />
              <ExperienceSection autoAdd={addExperience} />
              <ProjectsSection />
              <EducationSection />
              <CertificationsSection />
              <LanguagesSection />
              <StandardAnswersSection />
            </form>
            {previewOpen && (
              <div className="hidden xl:block">
                <CvPreviewPanel
                  data={fromForm(values)}
                  valid={errorCount === 0}
                  roleFamilies={values.role_profiles?.map((r) => r.name).filter(Boolean) ?? []}
                  onClose={() => setPreviewOpen(false)}
                />
              </div>
            )}
          </div>
          {dirty && (
            <div className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 shadow-overlay backdrop-blur">
              <div
                className="mx-auto flex max-w-content items-center gap-3 px-4 py-3 md:px-8"
                role="region"
                aria-label="Unsaved changes"
              >
                <p className="flex-1 text-body">
                  <span className="font-medium tabular">{changeCount}</span> unsaved change
                  {changeCount === 1 ? "" : "s"}
                  {errorCount > 0 && (
                    <span className="ml-2 text-danger">· fix the highlighted fields first</span>
                  )}
                </p>
                <Button variant="ghost" onClick={() => discard()}>
                  <RotateCcw /> Discard
                </Button>
                <Button onClick={onSubmit} loading={save.isPending}>
                  <Save /> Save
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </FormProvider>
  );
}
