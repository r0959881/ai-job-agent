import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Play, Search } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FolderNotice } from "@/features/settings/StorageCard";
import { Field } from "@/components/common";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Checkbox, Switch } from "@/components/ui/controls";
import { Badge, Input, Skeleton } from "@/components/ui/primitives";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/overlays";
import { ApiError, api } from "@/lib/api";
import { keys, useIntegrations, useSearchCatalog } from "@/lib/queries";
import type { Region, RunOptions, SearchCatalog, SearchSource, SourceKind } from "@/lib/types";
import { cn } from "@/lib/utils";

const WIZARD_STEPS = ["Regions", "Roles", "Sources"] as const;
const STORAGE_KEY = "run-scope";

const QUICK_PICKS = [
  { label: "Benelux", ids: ["BE", "NL", "LU"] },
  { label: "DACH", ids: ["DE", "AT", "CH"] },
  { label: "Nordics", ids: ["SE", "DK", "NO", "FI"] },
  { label: "Remote", ids: ["REMOTE"] },
];

const KIND_LABELS: Record<SourceKind, string> = {
  scraper: "Web scraping",
  api: "Job boards and APIs",
  email: "Email alerts",
};

type Scope = Pick<RunOptions, "regions" | "roles" | "languages" | "sources">;

/** The last scope used, so the next run starts from it. Browser storage may be unavailable. */
function loadScope(): Partial<Scope> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<Scope>;
  } catch {
    return {};
  }
}

function saveScope(scope: Scope) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(scope));
  } catch {
    // Remembering the choice is a convenience only.
  }
}

function initialScope(catalog: SearchCatalog): Scope {
  const saved = loadScope();
  const regionIds = new Set(catalog.regions.map((r) => r.id));
  const roleNames = new Set(catalog.roles.map((r) => r.name));
  const sourceKeys = new Set(catalog.sources.map((s) => s.key));
  const keep = (values: string[] | undefined, known: Set<string>) =>
    (values ?? []).filter((value) => known.has(value));
  const regions = keep(saved.regions, regionIds);
  const roles = keep(saved.roles, roleNames);
  const sources = keep(saved.sources, sourceKeys);
  // An empty saved list is a choice ("any language"), so only a missing one falls back to the default.
  const languages =
    saved.languages !== undefined
      ? keep(saved.languages, new Set(catalog.languages.map((l) => l.id)))
      : catalog.defaults.languages;
  return {
    regions: regions.length ? regions : catalog.defaults.regions,
    roles: roles.length ? roles : catalog.defaults.roles.filter((name) => roleNames.has(name)),
    languages,
    sources: sources.length
      ? sources
      : catalog.sources.filter((s) => s.default && s.configured).map((s) => s.key),
  };
}

/** Why a source cannot run for these regions, or "" when it can. */
function unavailableReason(source: SearchSource, regions: string[], regionById: Map<string, Region>) {
  if (!source.configured) return source.setup_hint;
  if (regions.some((id) => source.regions.includes(id))) return "";
  const names = source.regions.map((id) => regionById.get(id)?.label ?? id);
  return names.length <= 3 ? `Covers ${names.join(", ")} only.` : "Does not cover the selected regions.";
}

function toggle(list: string[], value: string, on: boolean) {
  return on ? [...new Set([...list, value])] : list.filter((item) => item !== value);
}

export function StartRunDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const catalog = useSearchCatalog(open);
  const integrations = useIntegrations();
  const [stepIndex, setStepIndex] = React.useState(0);
  const [scope, setScope] = React.useState<Scope>({ regions: [], roles: [], languages: [], sources: [] });
  const [options, setOptions] = React.useState({
    time_window_hours: 24,
    max_tailor: null as number | null,
    dry_run: false,
  });

  React.useEffect(() => {
    if (open && catalog.data) {
      setScope(initialScope(catalog.data));
      setOptions((current) => ({ ...current, time_window_hours: catalog.data.defaults.time_window_hours }));
      setStepIndex(0);
    }
  }, [open, catalog.data]);

  const regionById = React.useMemo(
    () => new Map((catalog.data?.regions ?? []).map((region) => [region.id, region])),
    [catalog.data],
  );
  const runnableSources = (catalog.data?.sources ?? []).filter(
    (source) => scope.sources.includes(source.key) && !unavailableReason(source, scope.regions, regionById),
  );

  const start = useMutation({
    mutationFn: () => {
      const body: RunOptions = { ...scope, ...options, sources: runnableSources.map((s) => s.key) };
      return api.post<{ id: number }>("/api/runs", body);
    },
    onSuccess: ({ id }) => {
      saveScope(scope);
      toast.success(`Run #${id} started`, { description: "Follow its progress on the run page." });
      queryClient.invalidateQueries({ queryKey: keys.runs });
      onOpenChange(false);
      navigate(`/runs/${id}`);
      if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission().catch(() => undefined);
      }
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        const runId = (error.detail as { run_id?: number })?.run_id;
        toast.error("A run is already in progress", {
          description: "Only one run can happen at a time.",
          action: runId ? { label: "Open it", onClick: () => navigate(`/runs/${runId}`) } : undefined,
        });
      } else {
        toast.error("The run did not start", { description: (error as Error).message });
      }
    },
  });

  const canContinue = [scope.regions.length > 0, scope.roles.length > 0, runnableSources.length > 0][
    stepIndex
  ];
  const last = stepIndex === WIZARD_STEPS.length - 1;
  const groqMissing = integrations.data?.groq.status === "missing";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Start a run</DialogTitle>
          <DialogDescription>
            Pick where to look and which roles to search. The agent searches job sites in those regions, keeps
            eligible jobs and tailors a CV for each new one.
          </DialogDescription>
        </DialogHeader>
        <ol className="flex gap-2" aria-label="Steps">
          {WIZARD_STEPS.map((label, index) => (
            <li key={label} className="flex-1">
              <button
                type="button"
                disabled={index > stepIndex}
                onClick={() => setStepIndex(index)}
                aria-current={index === stepIndex ? "step" : undefined}
                className={cn(
                  "flex w-full items-center gap-2 border-t-2 pt-2 text-left text-caption",
                  index <= stepIndex
                    ? "border-primary text-foreground"
                    : "border-border text-muted-foreground",
                )}
              >
                <span
                  className={cn(
                    "flex size-5 items-center justify-center rounded-full text-[0.7rem] tabular",
                    index < stepIndex ? "bg-primary text-primary-foreground" : "border",
                  )}
                >
                  {index < stepIndex ? <Check className="size-3" /> : index + 1}
                </span>
                {label}
              </button>
            </li>
          ))}
        </ol>

        {catalog.isError ? (
          <ErrorState
            title="Could not load the search options"
            error={catalog.error}
            onRetry={() => catalog.refetch()}
          />
        ) : !catalog.data ? (
          <div className="space-y-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <form
            className="space-y-5"
            onSubmit={(event) => {
              event.preventDefault();
              if (!canContinue) return;
              if (last) start.mutate();
              else setStepIndex(stepIndex + 1);
            }}
          >
            {stepIndex === 0 && (
              <>
                <RegionStep
                  catalog={catalog.data}
                  value={scope.regions}
                  onChange={(regions) => setScope({ ...scope, regions })}
                />
                <LanguageStep
                  catalog={catalog.data}
                  value={scope.languages}
                  onChange={(languages) => setScope({ ...scope, languages })}
                />
              </>
            )}
            {stepIndex === 1 && (
              <RoleStep
                catalog={catalog.data}
                value={scope.roles}
                onChange={(roles) => setScope({ ...scope, roles })}
                onNavigate={() => onOpenChange(false)}
              />
            )}
            {stepIndex === 2 && (
              <>
                <FolderNotice />
                <SourceStep
                  catalog={catalog.data}
                  regions={scope.regions}
                  regionById={regionById}
                  value={scope.sources}
                  onChange={(sources) => setScope({ ...scope, sources })}
                />
                <RunOptionsFields options={options} onChange={setOptions} />
                {groqMissing && !options.dry_run && (
                  <p className="rounded-md bg-warning-soft p-3 text-body text-warning">
                    GROQ_API_KEY is not set, so tailoring will be skipped. Add it in Settings → Integrations.
                  </p>
                )}
              </>
            )}

            <DialogFooter className="items-center gap-2 sm:justify-between">
              <p className="text-caption text-muted-foreground tabular">
                {scope.regions.length} region{scope.regions.length === 1 ? "" : "s"} · {scope.roles.length}{" "}
                role
                {scope.roles.length === 1 ? "" : "s"} ·{" "}
                {scope.languages.length
                  ? `${scope.languages.length} language${scope.languages.length === 1 ? "" : "s"}`
                  : "any language"}
                {stepIndex === 2 &&
                  ` · ${runnableSources.length} source${runnableSources.length === 1 ? "" : "s"}`}
              </p>
              <div className="flex gap-2">
                {stepIndex === 0 ? (
                  <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                    Cancel
                  </Button>
                ) : (
                  <Button type="button" variant="outline" onClick={() => setStepIndex(stepIndex - 1)}>
                    <ArrowLeft /> Back
                  </Button>
                )}
                {last ? (
                  <Button type="submit" loading={start.isPending} disabled={!canContinue}>
                    <Play /> Start run
                  </Button>
                ) : (
                  <Button type="submit" disabled={!canContinue}>
                    Next <ArrowRight />
                  </Button>
                )}
              </div>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function RegionStep({
  catalog,
  value,
  onChange,
}: {
  catalog: SearchCatalog;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [filter, setFilter] = React.useState("");
  const needle = filter.trim().toLowerCase();
  const visible = catalog.regions.filter((region) => region.label.toLowerCase().includes(needle));
  const selected = new Set(value);

  return (
    <fieldset className="space-y-3">
      <legend className="mb-1 text-body font-medium">Where should the agent look?</legend>
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[12rem] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Find a country"
            aria-label="Find a country"
            className="pl-8"
          />
        </div>
        {QUICK_PICKS.map((pick) => (
          <Button
            key={pick.label}
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onChange([...new Set([...value, ...pick.ids])])}
          >
            + {pick.label}
          </Button>
        ))}
        {value.length > 0 && (
          <Button type="button" size="sm" variant="ghost" onClick={() => onChange([])}>
            Clear
          </Button>
        )}
      </div>
      <div className="max-h-[17rem] space-y-4 overflow-y-auto pr-1">
        {catalog.groups.map((group) => {
          const regions = visible.filter((region) => region.group === group);
          if (!regions.length) return null;
          return (
            <section key={group} aria-label={group}>
              <h3 className="mb-1.5 text-caption font-medium text-muted-foreground">{group}</h3>
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                {regions.map((region) => {
                  const on = selected.has(region.id);
                  return (
                    <button
                      key={region.id}
                      type="button"
                      aria-pressed={on}
                      onClick={() => onChange(toggle(value, region.id, !on))}
                      className={cn(
                        "flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-body transition-colors",
                        on ? "border-primary bg-accent text-accent-foreground" : "hover:bg-muted/60",
                      )}
                    >
                      <span aria-hidden>{region.flag}</span>
                      <span className="flex-1 truncate">{region.label}</span>
                      {on && <Check className="size-4 shrink-0" />}
                    </button>
                  );
                })}
              </div>
            </section>
          );
        })}
        {!visible.length && <p className="text-body text-muted-foreground">No country matches “{filter}”.</p>}
      </div>
    </fieldset>
  );
}

function LanguageStep({
  catalog,
  value,
  onChange,
}: {
  catalog: SearchCatalog;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const selected = new Set(value);
  return (
    <fieldset className="space-y-2">
      <legend className="mb-1 text-body font-medium">Which job languages?</legend>
      <div className="flex flex-wrap gap-1.5">
        {catalog.languages.map((language) => {
          const on = selected.has(language.id);
          return (
            <button
              key={language.id}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(toggle(value, language.id, !on))}
              className={cn(
                "flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-body transition-colors",
                on ? "border-primary bg-accent text-accent-foreground" : "hover:bg-muted/60",
              )}
            >
              {language.label}
              {on && <Check className="size-3.5 shrink-0" />}
            </button>
          );
        })}
      </div>
      <p className="text-caption text-muted-foreground">
        {value.length
          ? "Keeps jobs that require only these languages. When a post names no language, it must be written in one of them."
          : "No language picked: jobs in every language are kept."}
      </p>
    </fieldset>
  );
}

function RoleStep({
  catalog,
  value,
  onChange,
  onNavigate,
}: {
  catalog: SearchCatalog;
  value: string[];
  onChange: (next: string[]) => void;
  onNavigate: () => void;
}) {
  const all = catalog.roles.map((role) => role.name);
  return (
    <fieldset className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <legend className="text-body font-medium">Which roles should it search and tailor CVs for?</legend>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => onChange(value.length === all.length ? [] : all)}
        >
          {value.length === all.length ? "Select none" : "Select all"}
        </Button>
      </div>
      <div className="max-h-[22rem] space-y-2 overflow-y-auto pr-1">
        {catalog.roles.map((role) => (
          <label
            key={role.name}
            className="flex items-start gap-3 rounded-md border p-3 hover:bg-muted/50 has-[:checked]:border-primary"
          >
            <Checkbox
              checked={value.includes(role.name)}
              onCheckedChange={(checked) => onChange(toggle(value, role.name, checked === true))}
              className="mt-0.5"
            />
            <span className="min-w-0 flex-1 space-y-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{role.name}</span>
                {!role.has_profile && <Badge variant="warning">No role profile</Badge>}
              </span>
              {role.focus && (
                <span className="line-clamp-2 block text-caption text-muted-foreground">{role.focus}</span>
              )}
              <span className="block text-caption">
                <span className="text-muted-foreground">Searches for </span>
                {role.queries.map((query) => `“${query}”`).join(", ")}
                {role.searches_by_name && (
                  <span className="text-muted-foreground">
                    {" "}
                    (the role name; add search terms in Settings)
                  </span>
                )}
              </span>
            </span>
          </label>
        ))}
      </div>
      <p className="text-caption text-muted-foreground">
        Roles come from your{" "}
        <Link to="/profile" onClick={onNavigate} className="underline underline-offset-2">
          role profiles
        </Link>{" "}
        and the target roles in{" "}
        <Link to="/settings" onClick={onNavigate} className="underline underline-offset-2">
          Settings → Search
        </Link>
        . A role without a profile gets your general CV.
      </p>
    </fieldset>
  );
}

function SourceStep({
  catalog,
  regions,
  regionById,
  value,
  onChange,
}: {
  catalog: SearchCatalog;
  regions: string[];
  regionById: Map<string, Region>;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <fieldset className="space-y-4">
      <legend className="mb-1 text-body font-medium">Where should it search?</legend>
      {(Object.keys(KIND_LABELS) as SourceKind[]).map((kind) => {
        const sources = catalog.sources.filter((source) => source.kind === kind);
        if (!sources.length) return null;
        return (
          <section key={kind} aria-label={KIND_LABELS[kind]} className="space-y-1.5">
            <h3 className="text-caption font-medium text-muted-foreground">{KIND_LABELS[kind]}</h3>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {sources.map((source) => {
                const reason = unavailableReason(source, regions, regionById);
                return (
                  <label
                    key={source.key}
                    className={cn(
                      "flex items-start gap-3 rounded-md border p-2.5",
                      reason ? "opacity-60" : "hover:bg-muted/50",
                    )}
                  >
                    <Checkbox
                      checked={!reason && value.includes(source.key)}
                      disabled={Boolean(reason)}
                      onCheckedChange={(checked) => onChange(toggle(value, source.key, checked === true))}
                      className="mt-0.5"
                    />
                    <span className="min-w-0">
                      <span className="block font-medium">{source.label}</span>
                      <span className="block text-caption text-muted-foreground">
                        {reason || source.description}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </section>
        );
      })}
    </fieldset>
  );
}

function RunOptionsFields({
  options,
  onChange,
}: {
  options: { time_window_hours: number; max_tailor: number | null; dry_run: boolean };
  onChange: (next: { time_window_hours: number; max_tailor: number | null; dry_run: boolean }) => void;
}) {
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Time window (hours)"
          htmlFor="run-window"
          description="Only jobs posted within this window."
        >
          <Input
            id="run-window"
            type="number"
            min={1}
            max={720}
            className="tabular"
            value={options.time_window_hours}
            onChange={(e) => onChange({ ...options, time_window_hours: Number(e.target.value) || 24 })}
          />
        </Field>
        <Field label="Max CVs to tailor" htmlFor="run-max" description="Leave empty for no limit.">
          <Input
            id="run-max"
            type="number"
            min={0}
            className="tabular"
            placeholder="No limit"
            value={options.max_tailor ?? ""}
            onChange={(e) =>
              onChange({
                ...options,
                max_tailor: e.target.value === "" ? null : Math.max(0, Number(e.target.value)),
              })
            }
          />
        </Field>
      </div>
      <label className="flex items-center justify-between gap-4 rounded-md border p-3">
        <span>
          <span className="block font-medium">Dry run</span>
          <span className="block text-caption text-muted-foreground">
            Discover and filter only. No CVs are generated.
          </span>
        </span>
        <Switch checked={options.dry_run} onCheckedChange={(dry_run) => onChange({ ...options, dry_run })} />
      </label>
    </>
  );
}
