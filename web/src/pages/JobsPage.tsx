import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef, RowSelectionState, SortingState } from "@tanstack/react-table";
import {
  Briefcase,
  Check,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Search,
  SkipForward,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  APPLICATION_STATUS_OPTIONS,
  ApplicationStatusBadge,
  JobStatusBadge,
  PageHeader,
  RelativeTime,
  SourceBadge,
} from "@/components/common";
import { useConfirm } from "@/components/confirm";
import { DataTable } from "@/components/data-table";
import { FilterMenu } from "@/components/filter-menu";
import { useStartRun } from "@/components/layout/RunControl";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox, Select } from "@/components/ui/controls";
import { Badge, Input } from "@/components/ui/primitives";
import { Tooltip } from "@/components/ui/overlays";
import { useJobFilters } from "@/features/jobs/useJobFilters";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { Job, JobsPage as JobsPageData } from "@/lib/types";
import { cn, formatSalary, formatShortDateTime } from "@/lib/utils";

const STATUS_OPTIONS = [
  { value: "new", label: "New" },
  { value: "processed", label: "CV ready" },
  { value: "rejected", label: "Filtered out" },
];

/** Jobs stay on the New jobs page this long, then move to Jobs (the same rule as the job store). */
const NEW_JOB_HOURS = 24;

// New jobs are all from the last 24 hours, and Jobs holds only older ones, so each page offers what still narrows it.
const ADDED_OPTIONS = {
  new: [
    { value: "any", label: "Added in the last 24 hours" },
    { value: "1h", label: "Added in the last hour" },
    { value: "run", label: "Found by the latest run" },
  ],
  all: [
    { value: "any", label: "Added any time" },
    { value: "7d", label: "Added in the last 7 days" },
  ],
};

/** When the job came into the app (not when the employer posted it). */
function AddedCell({ value, seen }: { value: string; seen?: string }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const fresh = Date.now() - new Date(value).getTime() < 3600_000;
  // Found again by a later run (more than an hour after it was first added).
  const seenAgain = seen && new Date(seen).getTime() - new Date(value).getTime() > 3600_000 ? seen : "";
  return (
    <span className="flex min-w-[7rem] flex-col gap-0.5">
      <span className="flex items-center gap-1.5">
        <RelativeTime value={value} />
        {fresh && <Badge variant="success">New</Badge>}
      </span>
      <span className="text-caption text-muted-foreground tabular">{formatShortDateTime(value)}</span>
      {seenAgain && (
        <span className="text-caption text-muted-foreground">
          seen again <RelativeTime value={seenAgain} />
        </span>
      )}
    </span>
  );
}

const QUICK = [
  { value: "ready", label: "Ready to apply" },
  { value: "applied_week", label: "Applied this week" },
  { value: "follow_up", label: "Follow-ups due" },
] as const;

function columns(): ColumnDef<Job, unknown>[] {
  return [
    {
      id: "select",
      enableSorting: false,
      size: 36,
      header: ({ table }) => (
        <Checkbox
          aria-label="Select all jobs on this page"
          checked={
            table.getIsAllRowsSelected() ? true : table.getIsSomeRowsSelected() ? "indeterminate" : false
          }
          onCheckedChange={(value) => table.toggleAllRowsSelected(value === true)}
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          aria-label={`Select ${row.original.title}`}
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(value === true)}
        />
      ),
    },
    {
      id: "title",
      accessorKey: "title",
      header: "Title",
      cell: ({ row }) => (
        <span className="line-clamp-2 max-w-[22rem] font-medium" title={row.original.title}>
          {row.original.title}
        </span>
      ),
    },
    {
      id: "company",
      accessorKey: "company",
      header: "Company",
      cell: ({ row }) => (
        <span className="line-clamp-2 min-w-[7rem] max-w-[12rem]" title={row.original.company}>
          {row.original.company}
        </span>
      ),
    },
    {
      id: "location",
      accessorKey: "location",
      header: "Location",
      cell: ({ row }) => (
        <span
          className="line-clamp-2 min-w-[7rem] max-w-[11rem] text-muted-foreground"
          title={row.original.location}
        >
          {row.original.location}
        </span>
      ),
    },
    {
      id: "role_family",
      accessorKey: "role_family",
      header: "Role family",
      cell: ({ row }) => row.original.role_family || "—",
    },
    {
      id: "source",
      accessorKey: "source",
      header: "Source",
      cell: ({ row }) => <SourceBadge source={row.original.source} />,
    },
    {
      id: "discovered",
      header: "Added",
      accessorKey: "discovered_at",
      cell: ({ row }) => <AddedCell value={row.original.discovered_at} seen={row.original.last_seen_at} />,
    },
    {
      id: "posted",
      header: "Posted",
      accessorFn: (job) => job.posted_at || job.discovered_at,
      cell: ({ row }) => <RelativeTime value={row.original.posted_at || row.original.discovered_at} />,
    },
    {
      id: "status",
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => <JobStatusBadge status={row.original.status} />,
    },
    {
      id: "application_status",
      accessorKey: "application_status",
      header: "Application",
      cell: ({ row }) => <ApplicationStatusBadge status={row.original.application_status} />,
    },
    {
      id: "has_cv",
      accessorKey: "has_cv",
      header: "CV",
      cell: ({ row }) =>
        row.original.has_cv ? (
          <Check className="size-4 text-success" aria-label="Has a tailored CV" />
        ) : (
          <X className="size-4 text-muted-foreground" aria-label="No CV yet" />
        ),
    },
    {
      id: "salary",
      header: "Salary",
      accessorFn: (job) => job.salary_max ?? job.salary_min,
      cell: ({ row }) => (
        <span className="tabular whitespace-nowrap">
          {formatSalary(row.original.salary_min, row.original.salary_max, row.original.salary_currency) ||
            "—"}
        </span>
      ),
    },
  ];
}

/** Jobs added in the last 24 hours, on a page of their own. */
export function NewJobsPage() {
  return <JobsPage view="new" />;
}

/** Above the Jobs list: how many jobs are on the New jobs page instead. */
function NewJobsBanner() {
  const fresh = useQuery({
    queryKey: keys.jobs("new=only&page_size=1"),
    queryFn: () => api.get<JobsPageData>("/api/jobs?new=only&page=1&page_size=1"),
  });
  const count = fresh.data?.total ?? 0;
  if (!count) return null;
  return (
    <Link
      to="/jobs/new"
      className="mb-4 flex items-center gap-2 rounded-lg border border-primary/30 bg-accent px-3 py-2 text-body hover:bg-accent/80"
    >
      <Sparkles className="size-4 text-primary" aria-hidden />
      <span>
        <span className="font-medium tabular">{count}</span> new job{count === 1 ? "" : "s"} found in the last{" "}
        {NEW_JOB_HOURS} hours. They move here after {NEW_JOB_HOURS} hours.
      </span>
      <span className="ml-auto font-medium text-primary">View new jobs →</span>
    </Link>
  );
}

export default function JobsPage({ view = "all" }: { view?: "all" | "new" }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const startRun = useStartRun();
  const { filters, update, clear, activeCount, apiQuery: filterQuery } = useJobFilters();
  const apiQuery = `${filterQuery}&new=${view === "new" ? "only" : "hide"}`;
  const [search, setSearch] = React.useState(filters.q);
  const [selection, setSelection] = React.useState<RowSelectionState>({});
  const cols = React.useMemo(columns, []);

  React.useEffect(() => setSearch(filters.q), [filters.q]);
  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      if (search !== filters.q) update({ q: search });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search, filters.q, update]);
  React.useEffect(() => setSelection({}), [apiQuery]);

  const jobs = useQuery({
    queryKey: keys.jobs(apiQuery),
    queryFn: () => api.get<JobsPageData>(`/api/jobs?${apiQuery}`),
    placeholderData: keepPreviousData,
  });
  const selectedIds = Object.keys(selection).filter((id) => selection[id]);

  const bulk = useMutation({
    mutationFn: (body: { ids: string[]; action: string; delete_files?: boolean }) =>
      api.post<{ done: string[]; failed: { id: string; reason: string }[] }>("/api/jobs/bulk", body),
    onSuccess: (result, body) => {
      const verb =
        body.action === "skip"
          ? "Marked as skipped"
          : body.action === "delete"
            ? "Deleted"
            : "Regenerated CVs for";
      const description = result.failed.length
        ? `${result.failed.length} failed: ${[...new Set(result.failed.map((f) => f.reason))].join("; ")}`
        : undefined;
      (result.failed.length ? toast.warning : toast.success)(`${verb} ${result.done.length} job(s)`, {
        description,
      });
      setSelection({});
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: keys.stats });
    },
    onError: (error: Error) => toast.error("The bulk action failed", { description: error.message }),
  });

  const sorting: SortingState = [{ id: filters.sort, desc: filters.order === "desc" }];
  const data = jobs.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const from = data && data.total ? (data.page - 1) * data.page_size + 1 : 0;
  const to = data ? Math.min(data.total, data.page * data.page_size) : 0;

  return (
    <>
      {view === "new" ? (
        <PageHeader
          title="New jobs"
          description={`Jobs found in the last ${NEW_JOB_HOURS} hours. After ${NEW_JOB_HOURS} hours each one moves to Jobs with the rest.`}
        />
      ) : (
        <>
          <PageHeader
            title="Jobs"
            description={`Every job the agent found more than ${NEW_JOB_HOURS} hours ago. Open one to get everything you need to apply.`}
          />
          <NewJobsBanner />
        </>
      )}
      <div className="mb-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-full max-w-sm">
            <Search
              className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground"
              aria-hidden
            />
            <Input
              type="search"
              aria-label="Search jobs"
              placeholder="Search title, company, location…"
              className="pl-8"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Quick filters">
            {QUICK.map((chip) => (
              <button
                key={chip.value}
                type="button"
                aria-pressed={filters.quick === chip.value}
                onClick={() => update({ quick: filters.quick === chip.value ? "" : chip.value })}
                className={cn(
                  "h-8 rounded-full border px-3 text-caption font-medium transition-colors hover:bg-muted",
                  filters.quick === chip.value &&
                    "border-primary bg-primary text-primary-foreground hover:bg-primary/90",
                )}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FilterMenu
            label="Status"
            options={STATUS_OPTIONS}
            value={filters.status}
            onChange={(status) => update({ status })}
          />
          <FilterMenu
            label="Application"
            options={APPLICATION_STATUS_OPTIONS}
            value={filters.application_status}
            onChange={(application_status) => update({ application_status })}
          />
          <FilterMenu
            label="Role family"
            options={(data?.facets.role_families ?? []).map((r) => ({ value: r, label: r }))}
            value={filters.role_family}
            onChange={(role_family) => update({ role_family })}
          />
          <FilterMenu
            label="Source"
            options={(data?.facets.sources ?? []).map((s) => ({ value: s, label: s }))}
            value={filters.source}
            onChange={(source) => update({ source })}
          />
          <div className="w-32">
            <Select
              aria-label="Has CV"
              value={filters.has_cv || "any"}
              onValueChange={(v) => update({ has_cv: v === "any" ? "" : (v as "true" | "false") })}
              options={[
                { value: "any", label: "Any CV state" },
                { value: "true", label: "Has CV" },
                { value: "false", label: "No CV" },
              ]}
              className="h-8 text-caption"
            />
          </div>
          <div className="w-52">
            <Select
              aria-label="Added to the app"
              value={filters.added || "any"}
              onValueChange={(v) => update({ added: v === "any" ? "" : (v as typeof filters.added) })}
              options={ADDED_OPTIONS[view]}
              className="h-8 text-caption"
            />
          </div>
          <label className="flex items-center gap-1.5 text-caption text-muted-foreground">
            Posted from
            <Input
              type="date"
              className="h-8 w-36 text-caption"
              value={filters.date_from}
              onChange={(e) => update({ date_from: e.target.value })}
            />
          </label>
          <label className="flex items-center gap-1.5 text-caption text-muted-foreground">
            to
            <Input
              type="date"
              className="h-8 w-36 text-caption"
              value={filters.date_to}
              onChange={(e) => update({ date_to: e.target.value })}
            />
          </label>
          {activeCount > 0 && (
            <Button variant="ghost" size="sm" onClick={clear}>
              <X /> Clear filters ({activeCount})
            </Button>
          )}
        </div>
      </div>

      {selectedIds.length > 0 && (
        <div
          className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-accent px-3 py-2"
          role="region"
          aria-label="Bulk actions"
        >
          <span className="text-body font-medium tabular">{selectedIds.length} selected</span>
          <Button
            size="sm"
            variant="outline"
            loading={bulk.isPending && bulk.variables?.action === "skip"}
            onClick={() => bulk.mutate({ ids: selectedIds, action: "skip" })}
          >
            <SkipForward /> Mark as skipped
          </Button>
          <Button
            size="sm"
            variant="outline"
            loading={bulk.isPending && bulk.variables?.action === "regenerate"}
            onClick={async () => {
              const ok = await confirm({
                title: `Regenerate ${selectedIds.length} CV(s)?`,
                description:
                  "Each CV asks Groq for a new summary and bullets. This takes about 5–15 seconds per job.",
                confirmLabel: "Regenerate",
              });
              if (ok) {
                toast.info(`Regenerating ${selectedIds.length} CV(s)…`, {
                  description: "Keep this tab open.",
                });
                bulk.mutate({ ids: selectedIds, action: "regenerate" });
              }
            }}
          >
            <RefreshCw /> Regenerate CVs
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="text-danger"
            onClick={async () => {
              const ok = await confirm({
                title: `Delete ${selectedIds.length} job(s)?`,
                description:
                  "The jobs are removed from the database together with their tailored CVs and cover letters. A future run may find them again.",
                confirmLabel: "Delete jobs and files",
                destructive: true,
              });
              if (ok) bulk.mutate({ ids: selectedIds, action: "delete", delete_files: true });
            }}
          >
            <Trash2 /> Delete
          </Button>
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setSelection({})}>
            Clear selection
          </Button>
        </div>
      )}

      {jobs.isPending && <SkeletonRows rows={10} />}
      {jobs.isError && <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />}
      {data &&
        data.total === 0 &&
        (activeCount ? (
          <EmptyState
            icon={Search}
            title="No jobs match these filters"
            description="Try removing a filter or searching for something else."
            action={
              <Button variant="outline" onClick={clear}>
                Clear filters
              </Button>
            }
          />
        ) : view === "new" ? (
          <EmptyState
            icon={Sparkles}
            title={`No new jobs in the last ${NEW_JOB_HOURS} hours`}
            description="Run the agent to look for jobs posted since the last run. Older jobs are on the Jobs page."
            action={
              <div className="flex gap-2">
                <Button onClick={startRun}>Run agent</Button>
                <Link to="/jobs" className={buttonVariants({ variant: "outline" })}>
                  All jobs
                </Link>
              </div>
            }
          />
        ) : (
          <EmptyState
            icon={Briefcase}
            title="No older jobs yet"
            description={`Jobs found in the last ${NEW_JOB_HOURS} hours are on the New jobs page; they move here after that.`}
            action={
              <div className="flex gap-2">
                <Link to="/jobs/new" className={buttonVariants()}>
                  New jobs
                </Link>
                <Button variant="outline" onClick={startRun}>
                  Run agent
                </Button>
              </div>
            }
          />
        ))}
      {data && data.total > 0 && (
        <>
          <div className={cn("transition-opacity", jobs.isFetching && "opacity-70")}>
            <DataTable
              caption="Jobs"
              data={data.items}
              columns={cols}
              getRowId={(job) => job.id}
              onRowClick={(job) => navigate(`/jobs/${job.id}`)}
              manualSorting
              sorting={sorting}
              onSortingChange={(updater) => {
                const next = typeof updater === "function" ? updater(sorting) : updater;
                const first = next[0];
                update({
                  sort: first?.id ?? "posted",
                  order: first ? (first.desc ? "desc" : "asc") : "desc",
                });
              }}
              rowSelection={selection}
              onRowSelectionChange={setSelection}
            />
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-body">
            <p className="tabular text-muted-foreground">
              Showing {from}–{to} of {data.total}
            </p>
            <div className="flex items-center gap-2">
              <div className="w-28">
                <Select
                  aria-label="Rows per page"
                  value={String(filters.page_size)}
                  onValueChange={(v) => update({ page_size: Number(v) })}
                  options={[25, 50, 100, 250].map((n) => ({ value: String(n), label: `${n} / page` }))}
                  className="h-8 text-caption"
                />
              </div>
              <Tooltip content="Previous page">
                <Button
                  size="icon-sm"
                  variant="outline"
                  aria-label="Previous page"
                  disabled={filters.page <= 1}
                  onClick={() => update({ page: filters.page - 1 }, false)}
                >
                  <ChevronLeft />
                </Button>
              </Tooltip>
              <span className="tabular">
                Page {filters.page} of {pages}
              </span>
              <Tooltip content="Next page">
                <Button
                  size="icon-sm"
                  variant="outline"
                  aria-label="Next page"
                  disabled={filters.page >= pages}
                  onClick={() => update({ page: filters.page + 1 }, false)}
                >
                  <ChevronRight />
                </Button>
              </Tooltip>
            </div>
          </div>
        </>
      )}
    </>
  );
}
