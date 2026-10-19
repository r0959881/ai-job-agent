import { DndContext, KeyboardSensor, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Plus, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";

import { Badge, Card, Input } from "@/components/ui/primitives";
import { humanize } from "@/features/profile/schema";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { Education, ImportResult, MergeAction, MergeItem, ResumeResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const SECTIONS: { id: string; title: string }[] = [
  { id: "personal_info", title: "Personal info" },
  { id: "experience", title: "Experience" },
  { id: "projects", title: "Projects" },
  { id: "education", title: "Education" },
  { id: "certifications", title: "Certifications" },
  { id: "languages", title: "Languages" },
];

export function defaultDecisions(items: MergeItem[]): Record<string, MergeAction> {
  return Object.fromEntries(items.map((item) => [item.id, item.status === "new" ? "add" : "keep_mine"]));
}

export function countOutcome(items: MergeItem[], decisions: Record<string, MergeAction>, skills: number) {
  let additions = skills;
  let changes = 0;
  for (const item of items) {
    const action = decisions[item.id];
    if (item.status === "new" && action === "add") additions++;
    if (item.status === "conflict" && action === "keep_both") additions++;
    if (item.status === "conflict" && action === "use_import") changes++;
  }
  return { additions, changes };
}

function Value({ value, changed = [] }: { value: unknown; changed?: string[] }) {
  if (value == null || value === "") return <span className="text-muted-foreground">Empty</span>;
  if (typeof value !== "object") return <span className={cn(changed.includes("value") && "rounded bg-warning-soft px-1")}>{String(value)}</span>;
  const record = value as Record<string, unknown>;
  const rows = Object.entries(record).filter(([, v]) => v !== "" && !(Array.isArray(v) && !v.length));
  return (
    <dl className="space-y-1 text-body">
      {rows.map(([key, v]) => (
        <div key={key} className={cn("rounded px-1", changed.includes(key) && "bg-warning-soft")}>
          <dt className="text-caption text-muted-foreground">{humanize(key)}</dt>
          <dd>
            {Array.isArray(v) ? (
              <ul className="list-disc pl-4">
                {v.map((line, i) => (
                  <li key={i}>{String(line)}</li>
                ))}
              </ul>
            ) : (
              String(v)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const STATUS_BADGE = {
  new: { label: "New", variant: "info" as const },
  matching: { label: "Matches existing", variant: "secondary" as const },
  conflict: { label: "Conflict", variant: "warning" as const },
};

function Choice({ options, value, onChange, label }: { options: { value: MergeAction; label: string }[]; value: MergeAction; onChange: (v: MergeAction) => void; label: string }) {
  return (
    <div className="inline-flex rounded-md border p-0.5" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded px-3 py-1 text-caption font-medium transition-colors",
            value === option.value ? "bg-primary text-primary-foreground" : "hover:bg-muted",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function ItemCard({ item, action, onChange, sourceLabel }: { item: MergeItem; action: MergeAction; onChange: (a: MergeAction) => void; sourceLabel: string }) {
  const badge = STATUS_BADGE[item.status];
  const single = item.section === "personal_info" || item.section === "education";
  return (
    <Card className={cn("space-y-3 p-3", item.status === "matching" && "opacity-70", item.low_confidence && "border-warning")}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 font-medium">{item.label || "Untitled"}</span>
        {item.low_confidence && (
          <Badge variant="warning"><AlertTriangle className="size-3" /> Check this</Badge>
        )}
        {item.ai_fields.length > 0 && (
          <Badge variant="accent"><Sparkles className="size-3" /> AI: {item.ai_fields.map(humanize).join(", ")}</Badge>
        )}
        <Badge variant={badge.variant}>{badge.label}</Badge>
      </div>
      {item.status === "conflict" ? (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-md border p-2">
              <p className="mb-1 text-caption font-semibold uppercase tracking-wide text-muted-foreground">Yours</p>
              <Value value={item.current} />
            </div>
            <div className="rounded-md border p-2">
              <p className="mb-1 text-caption font-semibold uppercase tracking-wide text-muted-foreground">{sourceLabel}</p>
              <Value value={item.imported} changed={item.changed_fields} />
            </div>
          </div>
          <Choice
            label={`Resolve ${item.label}`}
            value={action}
            onChange={onChange}
            options={[
              { value: "keep_mine", label: "Keep mine" },
              { value: "use_import", label: `Use ${sourceLabel}` },
              ...(single ? [] : [{ value: "keep_both" as MergeAction, label: "Keep both" }]),
            ]}
          />
        </>
      ) : item.status === "new" ? (
        <>
          {typeof item.imported === "object" && <Value value={item.imported} />}
          <Choice label={`Add ${item.label}`} value={action} onChange={onChange}
            options={[{ value: "add", label: "Add" }, { value: "skip", label: "Skip" }]} />
        </>
      ) : null}
    </Card>
  );
}

/* ---------------- skills pool ---------------- */

function SkillChip({ skill, category, categories, onAssign }: { skill: string; category: string; categories: string[]; onAssign: (c: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: `skill:${skill}` });
  return (
    <span
      ref={setNodeRef}
      style={transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined}
      className={cn("inline-flex items-center gap-1 rounded-full border bg-background py-0.5 pl-3 pr-1 text-caption shadow-sm", isDragging && "z-20 opacity-80 shadow-overlay")}
    >
      <span {...attributes} {...listeners} className="cursor-grab touch-none" aria-label={`Drag ${skill} to a category`}>
        {skill}
      </span>
      <select
        aria-label={`Category for ${skill}`}
        value={category}
        onChange={(e) => onAssign(e.target.value)}
        className="ml-1 rounded-full bg-muted px-1 py-0.5 text-caption outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <option value="">Don't add</option>
        {categories.map((c) => (
          <option key={c} value={c}>
            {humanize(c)}
          </option>
        ))}
      </select>
    </span>
  );
}

function CategoryDrop({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  const { isOver, setNodeRef } = useDroppable({ id: `category:${id}` });
  return (
    <div ref={setNodeRef} className={cn("min-h-16 rounded-md border border-dashed p-2 transition-colors", isOver && "border-primary bg-accent")}>
      <p className="mb-1.5 text-caption font-medium text-muted-foreground">{title}</p>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function SkillsPool({ pool, assignments, setAssignments, categories, setCategories }: {
  pool: string[];
  assignments: Record<string, string>;
  setAssignments: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  categories: string[];
  setCategories: React.Dispatch<React.SetStateAction<string[]>>;
}) {
  const [newCategory, setNewCategory] = React.useState("");
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor));
  const assign = (skill: string, category: string) => setAssignments((current) => ({ ...current, [skill]: category }));
  const onDragEnd = (event: DragEndEvent) => {
    const skill = String(event.active.id).replace(/^skill:/, "");
    const target = event.over ? String(event.over.id).replace(/^category:/, "") : null;
    if (target != null) assign(skill, target === "__pool" ? "" : target);
  };
  const chip = (skill: string) => (
    <SkillChip key={skill} skill={skill} category={assignments[skill] ?? ""} categories={categories} onAssign={(c) => assign(skill, c)} />
  );
  return (
    <DndContext sensors={sensors} onDragEnd={onDragEnd}>
      <div className="space-y-3">
        <CategoryDrop id="__pool" title="Not added yet: drag a skill into a category, or pick one from its menu">
          {pool.filter((s) => !assignments[s]).map(chip)}
          {pool.every((s) => assignments[s]) && <span className="text-caption text-muted-foreground">All skills are sorted.</span>}
        </CategoryDrop>
        <div className="grid gap-2 md:grid-cols-2">
          {categories.map((category) => (
            <CategoryDrop key={category} id={category} title={humanize(category)}>
              {pool.filter((s) => assignments[s] === category).map(chip)}
            </CategoryDrop>
          ))}
        </div>
        <form
          className="flex max-w-sm gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const name = newCategory.trim().toLowerCase().replace(/\s+/g, "_");
            if (name && !categories.includes(name)) setCategories([...categories, name]);
            setNewCategory("");
          }}
        >
          <Input aria-label="New skill category" placeholder="New category, e.g. cloud" value={newCategory} onChange={(e) => setNewCategory(e.target.value)} />
          <Button type="submit" variant="outline"><Plus /> Add</Button>
        </form>
      </div>
    </DndContext>
  );
}

/* ---------------- review ---------------- */

export function MergeReview({ result, onApplied, onBack }: { result: ImportResult; onApplied: () => void; onBack?: () => void }) {
  const queryClient = useQueryClient();
  const resume = useQuery({ queryKey: keys.resume, queryFn: () => api.get<ResumeResponse>("/api/resume") });
  const [decisions, setDecisions] = React.useState(() => defaultDecisions(result.items));
  const [assignments, setAssignments] = React.useState<Record<string, string>>(() => ({ ...result.skill_suggestions }));
  const [extraCategories, setExtraCategories] = React.useState<string[]>([]);
  const [educationIndex, setEducationIndex] = React.useState(0);
  const sourceLabel = result.source === "linkedin" ? "LinkedIn" : "the file";

  const baseCategories = Object.keys(resume.data?.data.core_skills ?? {});
  const suggested = Object.values(result.skill_suggestions);
  const categories = [...new Set([...baseCategories, ...suggested, ...extraCategories])];
  const assignedSkills = result.skills_pool.filter((s) => assignments[s]);
  const { additions, changes } = countOutcome(result.items, decisions, assignedSkills.length);

  const apply = useMutation({
    mutationFn: () => {
      const draft = { ...result.draft } as Record<string, unknown>;
      if (result.education_alternatives.length > 1) draft.education = result.education_alternatives[educationIndex];
      const skills: Record<string, string[]> = {};
      for (const skill of assignedSkills) (skills[assignments[skill]] ??= []).push(skill);
      return api.post<ResumeResponse>("/api/resume/import/commit", { draft, decisions, skills, etag: resume.data?.etag });
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(keys.resume, saved);
      queryClient.invalidateQueries({ queryKey: keys.backups });
      toast.success("Profile updated", { description: `${additions} addition(s) and ${changes} change(s) applied. A backup was saved first.` });
      onApplied();
    },
    onError: (error: Error) => toast.error("The import was not applied", { description: error.message }),
  });

  const setAll = (status: "new" | "conflict", action: MergeAction) =>
    setDecisions((current) => ({
      ...current,
      ...Object.fromEntries(result.items.filter((i) => i.status === status).map((i) => [i.id, action])),
    }));
  const newCount = result.items.filter((i) => i.status === "new").length;
  const conflictCount = result.items.filter((i) => i.status === "conflict").length;

  return (
    <div className="space-y-6 pb-24">
      <div className="flex flex-wrap items-center gap-2">
        <p className="flex-1 text-body text-muted-foreground tabular">
          {newCount} new · {conflictCount} conflict{conflictCount === 1 ? "" : "s"} ·{" "}
          {result.items.length - newCount - conflictCount} already in your profile
        </p>
        <Button size="sm" variant="outline" onClick={() => setAll("new", "add")} disabled={!newCount}>
          <Check /> Accept all new
        </Button>
        <Button size="sm" variant="outline" onClick={() => setAll("conflict", "keep_mine")} disabled={!conflictCount}>
          Keep mine for all conflicts
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setAll("conflict", "use_import")} disabled={!conflictCount}>
          Use {sourceLabel} for all conflicts
        </Button>
      </div>

      {result.warnings.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning-soft p-4" role="status">
          <p className="mb-1 font-medium text-warning">Worth knowing</p>
          <ul className="list-disc space-y-0.5 pl-5 text-body text-foreground/80">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {result.items.length === 0 && result.skills_pool.length === 0 && (
        <EmptyState title="Nothing to import" description="Everything in this export is already in your profile." />
      )}

      {SECTIONS.map((section) => {
        const items = result.items.filter((item) => item.section === section.id);
        if (!items.length && !(section.id === "education" && result.education_alternatives.length > 1)) return null;
        return (
          <section key={section.id} aria-labelledby={`merge-${section.id}`} className="space-y-2">
            <h2 id={`merge-${section.id}`} className="text-section">
              {section.title}
            </h2>
            {section.id === "education" && result.education_alternatives.length > 1 && (
              <fieldset className="space-y-1 rounded-md border p-3">
                <legend className="px-1 text-caption text-muted-foreground">Your profile holds one education entry. Pick which one to use:</legend>
                {result.education_alternatives.map((edu: Education, index) => (
                  <label key={index} className="flex items-center gap-2 text-body">
                    <input type="radio" name="education-choice" checked={educationIndex === index} onChange={() => setEducationIndex(index)} />
                    {[edu.degree, edu.institution, edu.dates].filter(Boolean).join(" · ")}
                  </label>
                ))}
              </fieldset>
            )}
            {items.map((item) => (
              <ItemCard
                key={item.id}
                item={item}
                sourceLabel={sourceLabel}
                action={decisions[item.id]}
                onChange={(action) => setDecisions((current) => ({ ...current, [item.id]: action }))}
              />
            ))}
          </section>
        );
      })}

      {result.skills_pool.length > 0 && (
        <section aria-labelledby="merge-skills" className="space-y-2">
          <h2 id="merge-skills" className="text-section">
            Skills <span className="text-body font-normal text-muted-foreground">({result.skills_pool.length} not yet in your profile)</span>
          </h2>
          <SkillsPool pool={result.skills_pool} assignments={assignments} setAssignments={setAssignments} categories={categories} setCategories={setExtraCategories} />
        </section>
      )}

      <div className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 shadow-overlay backdrop-blur">
        <div className="mx-auto flex max-w-content flex-wrap items-center gap-3 px-4 py-3 md:px-8">
          <p className="flex-1 text-body tabular" aria-live="polite">
            <strong>{additions}</strong> addition{additions === 1 ? "" : "s"}, <strong>{changes}</strong> change{changes === 1 ? "" : "s"}.
          </p>
          {onBack && (
            <Button variant="ghost" onClick={onBack}>
              Back
            </Button>
          )}
          <Button onClick={() => apply.mutate()} loading={apply.isPending} disabled={!resume.data}>
            Apply to profile
          </Button>
        </div>
      </div>
    </div>
  );
}

