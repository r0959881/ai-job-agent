import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Field, TagInput } from "@/components/common";
import { MultiSelect } from "@/components/multi-select";
import { useConfirm } from "@/components/confirm";
import { ErrorState, SkeletonForm } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/controls";
import { Card, Input, Textarea } from "@/components/ui/primitives";
import { SectionCard } from "@/features/profile/sections";
import { api } from "@/lib/api";
import { keys, useSearchCatalog } from "@/lib/queries";
import type { SearchSettings, SettingsResponse } from "@/lib/types";

interface RoleRow {
  id: string;
  name: string;
  keywords: string[];
  queries: string[];
}

let roleId = 0;
const toRows = (s: SearchSettings): RoleRow[] =>
  Object.entries(s.target_roles).map(([name, keywords]) => ({
    id: `r${++roleId}`,
    name,
    keywords,
    queries: s.search_queries[name] ?? [],
  }));

const LETTER_PARTS = [
  { key: "opening", label: "Opening" },
  { key: "evidence", label: "Evidence" },
  { key: "fit", label: "Why you fit" },
  { key: "closing", label: "Closing" },
] as const;
const EMPTY_LETTER = { opening: "", evidence: "", fit: "", closing: "" };

function CoverLetters({
  roles,
  letters,
  onChange,
}: {
  roles: string[];
  letters: SearchSettings["cover_letters"];
  onChange: (next: SearchSettings["cover_letters"]) => void;
}) {
  const [open, setOpen] = React.useState<string | null>(null);
  return (
    <div className="space-y-2">
      {roles.map((role) => {
        const letter = letters[role];
        const expanded = open === role;
        return (
          <div key={role} className="rounded-md border">
            <button
              type="button"
              className="flex w-full items-center gap-2 p-3 text-left hover:bg-muted/50"
              aria-expanded={expanded}
              onClick={() => setOpen(expanded ? null : role)}
            >
              {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
              <span className="flex-1 font-medium">{role}</span>
              <span className="text-caption text-muted-foreground">
                {letter ? "Custom text" : "Uses the general letter"}
              </span>
            </button>
            {expanded && (
              <div className="space-y-3 border-t p-3">
                {LETTER_PARTS.map(({ key, label }) => (
                  <Field key={key} label={label} htmlFor={`letter-${role}-${key}`}>
                    <Textarea
                      id={`letter-${role}-${key}`}
                      rows={3}
                      value={letter?.[key] ?? ""}
                      onChange={(e) =>
                        onChange({
                          ...letters,
                          [role]: { ...(letter ?? EMPTY_LETTER), [key]: e.target.value },
                        })
                      }
                    />
                  </Field>
                ))}
                {letter && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      const next = { ...letters };
                      delete next[role];
                      onChange(next);
                    }}
                  >
                    Use the general letter instead
                  </Button>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function SearchSettingsForm() {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const query = useQuery({
    queryKey: keys.settings,
    queryFn: () => api.get<SettingsResponse>("/api/settings/search"),
  });
  const catalog = useSearchCatalog();
  const regionLabels = new Map(
    (catalog.data?.regions ?? []).map((region) => [region.id, `${region.flag} ${region.label}`]),
  );
  const languageLabels = new Map(
    (catalog.data?.languages ?? []).map((language) => [language.id, language.label]),
  );
  const [draft, setDraft] = React.useState<SearchSettings | null>(null);
  const [roles, setRoles] = React.useState<RoleRow[]>([]);
  const [baseline, setBaseline] = React.useState("");

  const load = React.useCallback((settings: SearchSettings) => {
    setDraft(structuredClone(settings));
    const rows = toRows(settings);
    setRoles(rows);
    setBaseline(JSON.stringify(compose(settings, rows)));
  }, []);
  React.useEffect(() => {
    if (query.data && !draft) load(query.data.settings);
  }, [query.data, draft, load]);

  const save = useMutation({
    mutationFn: (settings: SearchSettings) => api.put<SettingsResponse>("/api/settings/search", { settings }),
    onSuccess: (result) => {
      queryClient.setQueryData(keys.settings, result);
      queryClient.invalidateQueries({ queryKey: keys.integrations });
      queryClient.invalidateQueries({ queryKey: keys.catalog });
      load(result.settings);
      toast.success("Search settings saved", { description: "The next run uses them." });
    },
    onError: (error: Error) => toast.error("Search settings were not saved", { description: error.message }),
  });

  if (query.isPending || !draft) return <SkeletonForm fields={8} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;

  const composed = compose(draft, roles);
  const dirty = JSON.stringify(composed) !== baseline;
  const set = <K extends keyof SearchSettings>(key: K, value: SearchSettings[K]) =>
    setDraft({ ...draft, [key]: value });
  const updateRole = (id: string, change: Partial<RoleRow>) =>
    setRoles(roles.map((r) => (r.id === id ? { ...r, ...change } : r)));
  const savedAllowed = query.data.settings.allowed_locations;

  const onSave = async () => {
    const removed = savedAllowed.filter((l) => !composed.allowed_locations.includes(l));
    if (removed.length) {
      const ok = await confirm({
        title: "Narrow the allowed locations?",
        description: (
          <>
            <p>You removed: {removed.join(", ")}.</p>
            <p className="mt-2">
              On the next run, stored jobs whose location matches none of the allowed places are deleted from
              the jobs database (this is how the agent has always worked). Their CV files stay in output/.
            </p>
          </>
        ),
        confirmLabel: "Save and narrow",
        destructive: true,
      });
      if (!ok) return;
    }
    save.mutate(composed);
  };

  return (
    <div className="space-y-6 pb-24">
      {query.data.warnings.length > 0 && (
        <div className="rounded-lg border border-warning/30 bg-warning-soft p-4 text-body" role="status">
          <ul className="list-disc space-y-0.5 pl-5 text-foreground/80">
            {query.data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <SectionCard
        id="roles"
        title="Target roles"
        description="Each role family has title keywords (to recognise jobs) and Adzuna search queries."
        actions={
          <Button
            size="sm"
            variant="outline"
            onClick={() => setRoles([...roles, { id: `r${++roleId}`, name: "", keywords: [], queries: [] }])}
          >
            <Plus /> Add role
          </Button>
        }
      >
        {roles.map((role, index) => (
          <Card key={role.id} className="space-y-3 p-3">
            <div className="flex items-end gap-2">
              <Field
                label="Role family"
                htmlFor={`role-${role.id}`}
                className="flex-1"
                error={!role.name.trim() ? "Give the role a name" : undefined}
              >
                <Input
                  id={`role-${role.id}`}
                  value={role.name}
                  onChange={(e) => updateRole(role.id, { name: e.target.value })}
                />
              </Field>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Delete role ${role.name || index + 1}`}
                disabled={roles.length === 1}
                onClick={() => setRoles(roles.filter((r) => r.id !== role.id))}
              >
                <Trash2 />
              </Button>
            </div>
            <Field
              label="Title keywords"
              htmlFor={`kw-${role.id}`}
              description="A job matches this role when its title or text contains one of these."
              error={!role.keywords.length ? "Add at least one keyword" : undefined}
            >
              <TagInput
                id={`kw-${role.id}`}
                value={role.keywords}
                onChange={(keywords) => updateRole(role.id, { keywords })}
              />
            </Field>
            <Field
              label="Adzuna search queries"
              htmlFor={`q-${role.id}`}
              description="Each query is one Adzuna search per run."
            >
              <TagInput
                id={`q-${role.id}`}
                value={role.queries}
                onChange={(queries) => updateRole(role.id, { queries })}
              />
            </Field>
          </Card>
        ))}
      </SectionCard>

      <SectionCard id="matching" title="Matching rules" description="Applied to every job from every source.">
        <Field
          label="Extra tech keywords"
          htmlFor="extra"
          description="A job also counts as relevant when it mentions one of these."
        >
          <TagInput id="extra" value={draft.extra_keywords} onChange={(v) => set("extra_keywords", v)} />
        </Field>
        <Field
          label="Entry-level signals"
          htmlFor="entry"
          description="Jobs need one of these (or ≤2 years of experience) unless they come from a trusted alert source."
        >
          <TagInput
            id="entry"
            value={draft.entry_level_keywords}
            onChange={(v) => set("entry_level_keywords", v)}
          />
        </Field>
        <Field
          label="Excluded title words (seniority)"
          htmlFor="exclude"
          description="Titles containing any of these are rejected."
        >
          <TagInput
            id="exclude"
            value={draft.exclude_title_keywords}
            onChange={(v) => set("exclude_title_keywords", v)}
          />
        </Field>
        <Field
          label="Trusted alert sources"
          htmlFor="trusted"
          description="Alerts from these sources skip the entry-level check."
        >
          <TagInput
            id="trusted"
            value={draft.trusted_alert_sources}
            onChange={(v) => set("trusted_alert_sources", v)}
          />
        </Field>
      </SectionCard>

      <SectionCard
        id="locations"
        title="Regions and locations"
        description="The Start-run dialog asks which regions to search. When you pick regions there, only jobs in those regions are kept."
      >
        <Field
          label="Default regions"
          htmlFor="regions"
          description="Preselected in the Start-run dialog, and searched by runs started from the command line."
          error={
            !draft.regions.length && !draft.allowed_locations.length
              ? "Pick at least one region or add an allowed place"
              : undefined
          }
        >
          <MultiSelect
            id="regions"
            aria-label="Default regions"
            value={draft.regions}
            onChange={(v) => set("regions", v)}
            options={(catalog.data?.regions ?? []).map((region) => region.id)}
            formatOption={(id) => regionLabels.get(id) ?? id}
            placeholder="Choose countries…"
          />
        </Field>
        <Field
          label="Default job languages"
          htmlFor="languages"
          description="Preselected in the Start-run dialog. Jobs must require only these languages, or be written in one of them. Leave empty to keep every language."
        >
          <MultiSelect
            id="languages"
            aria-label="Default job languages"
            value={draft.languages}
            onChange={(v) => set("languages", v)}
            options={(catalog.data?.languages ?? []).map((language) => language.id)}
            formatOption={(id) => languageLabels.get(id) ?? id}
            placeholder="Any language"
          />
        </Field>
        <Field
          label="Extra allowed places"
          htmlFor="allowed"
          description="Also accepted for runs that use the default regions, for example a town the region list does not know."
        >
          <TagInput
            id="allowed"
            value={draft.allowed_locations}
            onChange={(v) => set("allowed_locations", v)}
          />
        </Field>
        <Field
          label="Blocked locations"
          htmlFor="blocked"
          description="Jobs located here are rejected even if they also mention an allowed place."
        >
          <TagInput
            id="blocked"
            value={draft.blocked_locations}
            onChange={(v) => set("blocked_locations", v)}
          />
        </Field>
      </SectionCard>

      <SectionCard
        id="sources"
        title="Sources and time window"
        description="Sources switched on here are preselected when you start a run."
      >
        <div className="grid gap-4 md:grid-cols-3">
          <Field
            label="Time window (hours)"
            htmlFor="window"
            description="Jobs older than this are left out of the report."
          >
            <Input
              id="window"
              type="number"
              min={1}
              className="tabular"
              value={draft.time_window_hours}
              onChange={(e) => set("time_window_hours", Number(e.target.value) || 1)}
            />
          </Field>
          <Field
            label="Results per search"
            htmlFor="per-search"
            description="Per site, region and role. Higher means slower runs."
          >
            <Input
              id="per-search"
              type="number"
              min={5}
              max={100}
              className="tabular"
              value={draft.scraping.results_per_search}
              onChange={(e) =>
                set("scraping", { ...draft.scraping, results_per_search: Number(e.target.value) || 25 })
              }
            />
          </Field>
          <label className="flex items-start gap-3 self-end rounded-md border p-3 text-body">
            <Switch
              checked={draft.scraping.linkedin_descriptions}
              onCheckedChange={(on) => set("scraping", { ...draft.scraping, linkedin_descriptions: on })}
            />
            <span>
              <span className="block font-medium">Full LinkedIn descriptions</span>
              <span className="block text-caption text-muted-foreground">
                Needed to spot entry-level roles. About one second per job.
              </span>
            </span>
          </label>
        </div>
        <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {(catalog.data?.sources ?? []).map((source) => (
            <label key={source.key} className="flex items-center gap-2 text-body">
              <Switch
                checked={draft.sources[source.key] ?? source.default}
                onCheckedChange={(on) => set("sources", { ...draft.sources, [source.key]: on })}
              />
              {source.label}
            </label>
          ))}
        </div>
        <Field
          label="Companies to follow"
          htmlFor="company-boards"
          description="Their career pages are searched on every run. Write ats:company, as in the page's address: greenhouse:collibra (boards.greenhouse.io/collibra), lever:spotify, ashby:ramp, recruitee:bunq or smartrecruiters:BoschGroup."
        >
          <TagInput
            id="company-boards"
            value={draft.company_boards}
            onChange={(v) => set("company_boards", v)}
          />
        </Field>
        <Field
          label="Proxies (optional)"
          htmlFor="proxies"
          description="Only if LinkedIn or Indeed start blocking you, e.g. user:pass@host:port. Leave empty to connect directly."
        >
          <TagInput
            id="proxies"
            value={draft.scraping.proxies}
            onChange={(proxies) => set("scraping", { ...draft.scraping, proxies })}
          />
        </Field>
      </SectionCard>

      <SectionCard
        id="letters"
        title="Cover letter text"
        description="Paragraphs used for each role family's cover letter. The company and job title are filled in per job."
      >
        <CoverLetters
          roles={roles.map((r) => r.name).filter(Boolean)}
          letters={draft.cover_letters}
          onChange={(v) => set("cover_letters", v)}
        />
      </SectionCard>

      {dirty && (
        <div className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 shadow-overlay backdrop-blur">
          <div
            className="mx-auto flex max-w-content items-center gap-3 px-4 py-3 md:px-8"
            role="region"
            aria-label="Unsaved changes"
          >
            <p className="flex-1 text-body">Unsaved search settings</p>
            <Button variant="ghost" onClick={() => load(query.data.settings)}>
              <RotateCcw /> Discard
            </Button>
            <Button onClick={onSave} loading={save.isPending}>
              <Save /> Save
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function compose(settings: SearchSettings, roles: RoleRow[]): SearchSettings {
  const named = roles.filter((r) => r.name.trim());
  return {
    ...settings,
    target_roles: Object.fromEntries(named.map((r) => [r.name.trim(), r.keywords])),
    search_queries: Object.fromEntries(named.map((r) => [r.name.trim(), r.queries])),
  };
}
