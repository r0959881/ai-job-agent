import { ChevronDown, ChevronRight, Copy, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import {
  Controller,
  get,
  useFieldArray,
  useFormContext,
  useWatch,
  type FieldArrayPath,
  type FieldPath,
} from "react-hook-form";
import { toast } from "sonner";
import { Field, TagInput } from "@/components/common";
import { MultiSelect } from "@/components/multi-select";
import { DragHandle, SortableList, StringListEditor, type DragHandleProps } from "@/components/sortable";
import { Button } from "@/components/ui/button";
import { Card, Input, Textarea } from "@/components/ui/primitives";
import {
  emptyCertification,
  emptyExperience,
  emptyProject,
  humanize,
  type ProfileForm,
} from "@/features/profile/schema";
import { cn } from "@/lib/utils";

const fieldId = (path: string) => `f-${path.replace(/\./g, "-")}`;

function useFieldError(path: string): string | undefined {
  const { formState } = useFormContext<ProfileForm>();
  return get(formState.errors, path)?.message as string | undefined;
}

function TextField({
  path,
  label,
  description,
  multiline,
  placeholder,
  className,
}: {
  path: FieldPath<ProfileForm>;
  label: string;
  description?: string;
  multiline?: boolean;
  placeholder?: string;
  className?: string;
}) {
  const { register } = useFormContext<ProfileForm>();
  const error = useFieldError(path);
  const id = fieldId(path);
  const props = { id, placeholder, "aria-invalid": error ? true : undefined, ...register(path) };
  return (
    <Field label={label} htmlFor={id} description={description} error={error} className={className}>
      {multiline ? <Textarea rows={3} {...props} /> : <Input {...props} />}
    </Field>
  );
}

export function SectionCard({
  id,
  title,
  description,
  actions,
  children,
}: {
  id: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-20">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3 border-b p-4">
          <div className="space-y-0.5">
            <h2 id={`${id}-title`} className="text-section">
              {title}
            </h2>
            {description && <p className="max-w-prose text-body text-muted-foreground">{description}</p>}
          </div>
          {actions}
        </div>
        <div className="space-y-4 p-4">{children}</div>
      </Card>
    </section>
  );
}

/* ------------------------------------------------------------ list item card */

function ItemCard({
  title,
  subtitle,
  handle,
  label,
  open,
  onToggle,
  onDuplicate,
  onDelete,
  hasError,
  children,
}: {
  title: string;
  subtitle?: string;
  handle: Omit<DragHandleProps, "label">;
  label: string;
  open: boolean;
  onToggle: () => void;
  onDuplicate?: () => void;
  onDelete: () => void;
  hasError?: boolean;
  children: React.ReactNode;
}) {
  const contentId = React.useId();
  return (
    <div className={cn("rounded-md border bg-background", hasError && "border-danger")}>
      <div className="flex items-center gap-1 p-1.5">
        <DragHandle {...handle} label={label} />
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={contentId}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-muted/60"
        >
          {open ? <ChevronDown className="size-4 shrink-0" /> : <ChevronRight className="size-4 shrink-0" />}
          <span className="min-w-0">
            <span className={cn("block truncate font-medium", !title && "italic text-muted-foreground")}>
              {title || "Untitled"}
            </span>
            {subtitle && <span className="block truncate text-caption text-muted-foreground">{subtitle}</span>}
          </span>
        </button>
        {onDuplicate && (
          <Button type="button" variant="ghost" size="icon-sm" onClick={onDuplicate} aria-label={`Duplicate ${label}`}>
            <Copy />
          </Button>
        )}
        <Button type="button" variant="ghost" size="icon-sm" onClick={onDelete} aria-label={`Delete ${label}`}>
          <Trash2 />
        </Button>
      </div>
      {open && (
        <div id={contentId} className="space-y-4 border-t p-4">
          {children}
        </div>
      )}
    </div>
  );
}

/** Field-array helpers shared by every list section: open state, duplicate, delete with undo. */
function useListSection<Name extends FieldArrayPath<ProfileForm>>(name: Name, noun: string) {
  const { control, getValues, formState } = useFormContext<ProfileForm>();
  const array = useFieldArray({ control, name });
  const [open, setOpen] = React.useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const errors = get(formState.errors, name) as unknown[] | undefined;
  const hasError = (index: number) => Boolean(errors?.[index]);

  const append = (value: Parameters<typeof array.append>[0]) => {
    array.append(value);
    // Open the new item; its id is only known after render.
    window.setTimeout(() => {
      const fields = document.querySelectorAll(`[data-section="${name}"] [data-item]`);
      const last = fields[fields.length - 1] as HTMLElement | undefined;
      last?.querySelector<HTMLButtonElement>("button[aria-expanded='false']")?.click();
      last?.querySelector<HTMLInputElement>("input")?.focus();
    }, 0);
  };
  const duplicate = (index: number) => {
    const copy = structuredClone(getValues(`${name}.${index}` as FieldPath<ProfileForm>));
    array.insert(index + 1, copy as never);
    toast.success(`${noun} duplicated`);
  };
  const removeWithUndo = (index: number, label: string) => {
    const removed = structuredClone(getValues(`${name}.${index}` as FieldPath<ProfileForm>));
    array.remove(index);
    toast(`Removed ${label || noun.toLowerCase()}`, {
      description: "Nothing is saved until you click Save.",
      action: { label: "Undo", onClick: () => array.insert(index, removed as never) },
    });
  };
  return { ...array, open, toggle, hasError, append, duplicate, removeWithUndo };
}

/* ------------------------------------------------------------ sections */

export function PersonalInfoSection() {
  return (
    <SectionCard id="personal" title="Personal info" description="Shown at the top of every CV and cover letter.">
      <TextField path="personal_info.full_name" label="Full name" description="Also used to name generated files." />
      <TextField
        path="personal_info.headline"
        label="Headline"
        description="One line under your name, e.g. “Data Engineer (Databricks, PySpark)”."
      />
      <div className="grid gap-4 md:grid-cols-2">
        <TextField path="personal_info.email" label="Email" />
        <TextField path="personal_info.phone" label="Phone" />
      </div>
      <TextField path="personal_info.location" label="Location" placeholder="City, Country" />
    </SectionCard>
  );
}

export function RoleProfilesSection({ targetRoles }: { targetRoles: string[] }) {
  const { control } = useFormContext<ProfileForm>();
  const list = useListSection("role_profiles", "Role profile");
  const values_role_profiles = useWatch({ control, name: "role_profiles" }) ?? [];
  const categories = (useWatch({ control, name: "core_skills" }) ?? []).map((c) => c.name).filter(Boolean);
  const projects = (useWatch({ control, name: "projects" }) ?? []).map((p) => p.title).filter(Boolean);
  const names = new Set(values_role_profiles.map((profile) => profile.name));
  const missingRoles = targetRoles.filter((role) => !names.has(role));

  return (
    <SectionCard
      id="role-profiles"
      title="Role profiles"
      description="Each target role family gets its own focus, keywords and the skills and projects its CV shows."
      actions={
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() =>
            list.append({
              name: missingRoles[0] ?? "",
              focus: "",
              keywords: [],
              preferred_skill_categories: [],
              preferred_projects: [],
            })
          }
        >
          <Plus /> Add role profile
        </Button>
      }
    >
      {missingRoles.length > 0 && (
        <p className="rounded-md bg-warning-soft p-3 text-body text-warning">
          No profile yet for: {missingRoles.join(", ")}. CVs for these roles include every skill and project.
        </p>
      )}
      <div data-section="role_profiles">
        <SortableList
          items={list.fields}
          getId={(field) => field.id}
          onMove={list.move}
          className="space-y-2"
          renderItem={(field, index, handle) => (
            <div data-item>
              <ItemCard
                title={(values_role_profiles[index]?.name ?? "")}
                subtitle={(values_role_profiles[index]?.focus ?? "")}
                handle={handle}
                label={`role profile ${index + 1}`}
                open={list.open.has(field.id) || list.hasError(index)}
                onToggle={() => list.toggle(field.id)}
                onDuplicate={() => list.duplicate(index)}
                onDelete={() => list.removeWithUndo(index, (values_role_profiles[index]?.name ?? ""))}
                hasError={list.hasError(index)}
              >
                <TextField
                  path={`role_profiles.${index}.name`}
                  label="Role family"
                  description={
                    targetRoles.length
                      ? `Must match a target role in Settings → Search: ${targetRoles.join(", ")}.`
                      : undefined
                  }
                />
                <TextField path={`role_profiles.${index}.focus`} label="Focus" multiline />
                <Controller
                  control={control}
                  name={`role_profiles.${index}.keywords`}
                  render={({ field: f }) => (
                    <Field label="Keywords" htmlFor={fieldId(f.name)} description="Listed as “Key skills” on the CV.">
                      <TagInput id={fieldId(f.name)} value={f.value} onChange={f.onChange} />
                    </Field>
                  )}
                />
                <Controller
                  control={control}
                  name={`role_profiles.${index}.preferred_skill_categories`}
                  render={({ field: f }) => (
                    <Field label="Skill categories on the CV" htmlFor={fieldId(f.name)} description="Empty means all.">
                      <MultiSelect
                        id={fieldId(f.name)}
                        value={f.value}
                        onChange={f.onChange}
                        options={categories}
                        formatOption={humanize}
                        missingHint="This skill category no longer exists"
                      />
                    </Field>
                  )}
                />
                <Controller
                  control={control}
                  name={`role_profiles.${index}.preferred_projects`}
                  render={({ field: f }) => (
                    <Field label="Projects on the CV" htmlFor={fieldId(f.name)} description="Empty means all.">
                      <MultiSelect
                        id={fieldId(f.name)}
                        value={f.value}
                        onChange={f.onChange}
                        options={projects}
                        missingHint="This project no longer exists"
                      />
                    </Field>
                  )}
                />
              </ItemCard>
            </div>
          )}
        />
      </div>
    </SectionCard>
  );
}

/** Rename a value everywhere role profiles reference it (skill categories or project titles). */
function useRenamePropagation(kind: "preferred_skill_categories" | "preferred_projects") {
  const { getValues, setValue } = useFormContext<ProfileForm>();
  const before = React.useRef<string>("");
  return {
    onFocus: (value: string) => {
      before.current = value;
    },
    onBlur: (value: string) => {
      const old = before.current;
      if (!old || !value || old === value) return;
      let touched = 0;
      getValues("role_profiles").forEach((profile, index) => {
        if (profile[kind].includes(old)) {
          touched++;
          setValue(
            `role_profiles.${index}.${kind}`,
            profile[kind].map((v) => (v === old ? value : v)),
            { shouldDirty: true },
          );
        }
      });
      if (touched) toast.info(`Updated ${touched} role profile${touched === 1 ? "" : "s"} to use “${value}”.`);
    },
  };
}

export function SkillsSection() {
  const { control, register, formState } = useFormContext<ProfileForm>();
  const list = useListSection("core_skills", "Skill category");
  const values_core_skills = useWatch({ control, name: "core_skills" }) ?? [];
  const rename = useRenamePropagation("preferred_skill_categories");
  return (
    <SectionCard
      id="skills"
      title="Skills"
      description="Grouped by category. Role profiles choose which categories each CV shows."
      actions={
        <Button type="button" size="sm" variant="outline" onClick={() => list.append({ name: "", skills: [] })}>
          <Plus /> Add category
        </Button>
      }
    >
      <div data-section="core_skills">
        <SortableList
          items={list.fields}
          getId={(field) => field.id}
          onMove={list.move}
          className="space-y-2"
          renderItem={(_field, index, handle) => {
            const nameField = register(`core_skills.${index}.name`);
            return (
              <div data-item className={cn("rounded-md border p-3", list.hasError(index) && "border-danger")}>
                <div className="flex items-start gap-2">
                  <DragHandle {...handle} label={`skill category ${index + 1}`} />
                  <div className="flex-1 space-y-2">
                    <Field
                      label="Category"
                      htmlFor={fieldId(`core_skills.${index}.name`)}
                      error={get(formState.errors, `core_skills.${index}.name`)?.message}
                      description={humanize((values_core_skills[index]?.name ?? "")) || undefined}
                    >
                      <Input
                        id={fieldId(`core_skills.${index}.name`)}
                        placeholder="e.g. platforms_and_cloud"
                        {...nameField}
                        onFocus={(e) => rename.onFocus(e.target.value)}
                        onBlur={(e) => {
                          nameField.onBlur(e);
                          rename.onBlur(e.target.value);
                        }}
                      />
                    </Field>
                    <Controller
                      control={control}
                      name={`core_skills.${index}.skills`}
                      render={({ field: f }) => (
                        <TagInput
                          aria-label={`Skills in category ${index + 1}`}
                          value={f.value}
                          onChange={f.onChange}
                          placeholder="Add a skill and press Enter"
                        />
                      )}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Delete skill category ${index + 1}`}
                    onClick={() =>
                      list.removeWithUndo(index, (values_core_skills[index]?.name ?? ""))
                    }
                  >
                    <Trash2 />
                  </Button>
                </div>
              </div>
            );
          }}
        />
      </div>
    </SectionCard>
  );
}

export function ExperienceSection({ autoAdd }: { autoAdd?: boolean }) {
  const { control } = useFormContext<ProfileForm>();
  const list = useListSection("experience", "Experience");
  const values_experience = useWatch({ control, name: "experience" }) ?? [];
  const added = React.useRef(false);
  React.useEffect(() => {
    if (autoAdd && !added.current) {
      added.current = true;
      list.append(emptyExperience());
    }
  }, [autoAdd, list]);
  return (
    <SectionCard
      id="experience"
      title="Experience"
      description="Most recent first. The agent rephrases these bullets for each job but never invents new ones."
      actions={
        <Button type="button" size="sm" variant="outline" onClick={() => list.append(emptyExperience())}>
          <Plus /> Add experience
        </Button>
      }
    >
      <div data-section="experience">
        <SortableList
          items={list.fields}
          getId={(field) => field.id}
          onMove={list.move}
          className="space-y-2"
          renderItem={(field, index, handle) => {
            const role = (values_experience[index]?.role ?? "");
            const company = (values_experience[index]?.company ?? "");
            return (
              <div data-item>
                <ItemCard
                  title={[role, company].filter(Boolean).join(" · ")}
                  subtitle={(values_experience[index]?.dates ?? "")}
                  handle={handle}
                  label={`experience ${index + 1}`}
                  open={list.open.has(field.id) || list.hasError(index)}
                  onToggle={() => list.toggle(field.id)}
                  onDuplicate={() => list.duplicate(index)}
                  onDelete={() => list.removeWithUndo(index, role || company)}
                  hasError={list.hasError(index)}
                >
                  <div className="grid gap-4 md:grid-cols-2">
                    <TextField path={`experience.${index}.role`} label="Role" />
                    <TextField path={`experience.${index}.company`} label="Company" />
                    <TextField path={`experience.${index}.location`} label="Location" />
                    <TextField path={`experience.${index}.dates`} label="Dates" placeholder="Jun 2026 - Present" />
                  </div>
                  <TextField
                    path={`experience.${index}.type`}
                    label="Type"
                    placeholder="Professional Experience, Internship…"
                  />
                  <Controller
                    control={control}
                    name={`experience.${index}.bullets`}
                    render={({ field: f }) => (
                      <Field label="Bullets" description="Drag to reorder. Ctrl+Enter adds a new bullet below.">
                        <StringListEditor value={f.value} onChange={f.onChange} itemLabel="Bullet" addLabel="Add bullet" />
                      </Field>
                    )}
                  />
                </ItemCard>
              </div>
            );
          }}
        />
      </div>
    </SectionCard>
  );
}

export function ProjectsSection() {
  const { control, register, formState } = useFormContext<ProfileForm>();
  const list = useListSection("projects", "Project");
  const values_projects = useWatch({ control, name: "projects" }) ?? [];
  const rename = useRenamePropagation("preferred_projects");
  return (
    <SectionCard
      id="projects"
      title="Projects"
      description="Role profiles pick which projects appear on each CV."
      actions={
        <Button type="button" size="sm" variant="outline" onClick={() => list.append(emptyProject())}>
          <Plus /> Add project
        </Button>
      }
    >
      <div data-section="projects">
        <SortableList
          items={list.fields}
          getId={(field) => field.id}
          onMove={list.move}
          className="space-y-2"
          renderItem={(field, index, handle) => {
            const title = (values_projects[index]?.title ?? "");
            const titleField = register(`projects.${index}.title`);
            const error = get(formState.errors, `projects.${index}.title`)?.message;
            return (
              <div data-item>
                <ItemCard
                  title={title}
                  subtitle={(values_projects[index]?.tech_stack ?? "")}
                  handle={handle}
                  label={`project ${index + 1}`}
                  open={list.open.has(field.id) || list.hasError(index)}
                  onToggle={() => list.toggle(field.id)}
                  onDuplicate={() => list.duplicate(index)}
                  onDelete={() => list.removeWithUndo(index, title)}
                  hasError={list.hasError(index)}
                >
                  <Field label="Title" htmlFor={fieldId(`projects.${index}.title`)} error={error}
                    description="Renaming updates every role profile that lists this project.">
                    <Input
                      id={fieldId(`projects.${index}.title`)}
                      aria-invalid={error ? true : undefined}
                      {...titleField}
                      onFocus={(e) => rename.onFocus(e.target.value)}
                      onBlur={(e) => {
                        titleField.onBlur(e);
                        rename.onBlur(e.target.value);
                      }}
                    />
                  </Field>
                  <TextField path={`projects.${index}.tech_stack`} label="Tech stack" />
                  <Controller
                    control={control}
                    name={`projects.${index}.highlights`}
                    render={({ field: f }) => (
                      <Field label="Highlights">
                        <StringListEditor
                          value={f.value}
                          onChange={f.onChange}
                          itemLabel="Highlight"
                          addLabel="Add highlight"
                        />
                      </Field>
                    )}
                  />
                </ItemCard>
              </div>
            );
          }}
        />
      </div>
    </SectionCard>
  );
}

export function EducationSection() {
  const { control } = useFormContext<ProfileForm>();
  return (
    <SectionCard id="education" title="Education" description="Your most recent degree. The CV shows one entry.">
      <TextField path="education.degree" label="Degree" />
      <TextField path="education.institution" label="Institution" />
      <div className="grid gap-4 md:grid-cols-2">
        <TextField path="education.location" label="Location" />
        <TextField path="education.dates" label="Dates" placeholder="2023 - 2026" />
      </div>
      <Controller
        control={control}
        name="education.coursework"
        render={({ field: f }) => (
          <Field label="Key coursework" htmlFor="f-coursework">
            <TagInput id="f-coursework" value={f.value} onChange={f.onChange} />
          </Field>
        )}
      />
    </SectionCard>
  );
}

export function CertificationsSection() {
  const { control } = useFormContext<ProfileForm>();
  const list = useListSection("certifications", "Certification");
  const values_certifications = useWatch({ control, name: "certifications" }) ?? [];
  return (
    <SectionCard
      id="certifications"
      title="Certifications"
      actions={
        <Button type="button" size="sm" variant="outline" onClick={() => list.append(emptyCertification())}>
          <Plus /> Add certification
        </Button>
      }
    >
      <div data-section="certifications">
        <SortableList
          items={list.fields}
          getId={(field) => field.id}
          onMove={list.move}
          className="space-y-2"
          renderItem={(field, index, handle) => {
            const name = (values_certifications[index]?.name ?? "");
            return (
              <div data-item>
                <ItemCard
                  title={name}
                  subtitle={[(values_certifications[index]?.issuer ?? ""), (values_certifications[index]?.year ?? "")]
                    .filter(Boolean)
                    .join(", ")}
                  handle={handle}
                  label={`certification ${index + 1}`}
                  open={list.open.has(field.id) || list.hasError(index)}
                  onToggle={() => list.toggle(field.id)}
                  onDuplicate={() => list.duplicate(index)}
                  onDelete={() => list.removeWithUndo(index, name)}
                  hasError={list.hasError(index)}
                >
                  <TextField path={`certifications.${index}.name`} label="Name" />
                  <div className="grid gap-4 md:grid-cols-2">
                    <TextField path={`certifications.${index}.issuer`} label="Issuer" />
                    <TextField path={`certifications.${index}.year`} label="Year" />
                  </div>
                </ItemCard>
              </div>
            );
          }}
        />
      </div>
    </SectionCard>
  );
}

export function LanguagesSection() {
  const { register, formState } = useFormContext<ProfileForm>();
  const list = useListSection("languages", "Language");
  return (
    <SectionCard
      id="languages"
      title="Languages"
      description="Written as “Language: level”, e.g. “Dutch: B1”."
      actions={
        <Button type="button" size="sm" variant="outline" onClick={() => list.append({ value: "" })}>
          <Plus /> Add language
        </Button>
      }
    >
      <div data-section="languages">
        <SortableList
          items={list.fields}
          getId={(field) => field.id}
          onMove={list.move}
          className="space-y-2"
          renderItem={(_field, index, handle) => {
            const error = get(formState.errors, `languages.${index}.value`)?.message;
            return (
              <div data-item className="flex items-start gap-1">
                <DragHandle {...handle} label={`language ${index + 1}`} />
                <div className="flex-1">
                  <Input
                    aria-label={`Language ${index + 1}`}
                    aria-invalid={error ? true : undefined}
                    {...register(`languages.${index}.value`)}
                  />
                  {error && <p className="mt-1 text-caption text-danger">{error}</p>}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Delete language ${index + 1}`}
                  onClick={() => list.removeWithUndo(index, "language")}
                >
                  <Trash2 />
                </Button>
              </div>
            );
          }}
        />
      </div>
    </SectionCard>
  );
}

export function StandardAnswersSection() {
  const { register, formState } = useFormContext<ProfileForm>();
  const list = useListSection("standard_answers", "Answer");
  return (
    <SectionCard
      id="answers"
      title="Standard answers"
      description="Copy-ready answers for application forms: work authorisation, notice period, salary…"
      actions={
        <Button type="button" size="sm" variant="outline" onClick={() => list.append({ key: "", value: "" })}>
          <Plus /> Add answer
        </Button>
      }
    >
      <div data-section="standard_answers">
        <SortableList
          items={list.fields}
          getId={(field) => field.id}
          onMove={list.move}
          className="space-y-2"
          renderItem={(_field, index, handle) => {
            const keyError = get(formState.errors, `standard_answers.${index}.key`)?.message;
            return (
              <div data-item className="flex items-start gap-1">
                <DragHandle {...handle} label={`answer ${index + 1}`} />
                <div className="grid flex-1 gap-2 md:grid-cols-[minmax(0,14rem)_1fr]">
                  <div>
                    <Input
                      aria-label={`Question ${index + 1}`}
                      placeholder="notice_period"
                      aria-invalid={keyError ? true : undefined}
                      {...register(`standard_answers.${index}.key`)}
                    />
                    {keyError && <p className="mt-1 text-caption text-danger">{keyError}</p>}
                  </div>
                  <Input aria-label={`Answer ${index + 1}`} {...register(`standard_answers.${index}.value`)} />
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Delete answer ${index + 1}`}
                  onClick={() => list.removeWithUndo(index, "answer")}
                >
                  <Trash2 />
                </Button>
              </div>
            );
          }}
        />
      </div>
    </SectionCard>
  );
}
