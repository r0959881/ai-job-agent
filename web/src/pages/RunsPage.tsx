import type { ColumnDef } from "@tanstack/react-table";
import { History, Play } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { PageHeader, RelativeTime, RunStatusBadge } from "@/components/common";
import { DataTable } from "@/components/data-table";
import { useStartRun } from "@/components/layout/RunControl";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useRunsList } from "@/lib/queries";
import type { Run } from "@/lib/types";
import { formatDuration } from "@/lib/utils";

const num = (value: number) => <span className="tabular">{value}</span>;

const columns: ColumnDef<Run, unknown>[] = [
  {
    accessorKey: "id",
    header: "Run",
    cell: ({ row }) => <span className="tabular font-medium">#{row.original.id}</span>,
    size: 70,
  },
  {
    accessorKey: "started_at",
    header: "Started",
    cell: ({ row }) => <RelativeTime value={row.original.started_at} />,
  },
  {
    accessorKey: "duration_seconds",
    header: "Duration",
    cell: ({ row }) => (
      <span className="tabular">
        {row.original.status === "running" ? "Running…" : formatDuration(row.original.duration_seconds)}
      </span>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <RunStatusBadge status={row.original.status} />,
  },
  { accessorKey: "new", header: "New jobs", cell: ({ row }) => num(row.original.new) },
  { accessorKey: "filtered", header: "Filtered", cell: ({ row }) => num(row.original.filtered) },
  { accessorKey: "tailored", header: "CVs", cell: ({ row }) => num(row.original.tailored) },
  {
    accessorKey: "failed",
    header: "Failed",
    cell: ({ row }) => (
      <span className={row.original.failed ? "tabular font-medium text-danger" : "tabular"}>
        {row.original.failed}
      </span>
    ),
  },
  {
    id: "options",
    header: "Options",
    enableSorting: false,
    cell: ({ row }) => {
      const o = row.original.options ?? {};
      const parts = [
        o.dry_run ? "Dry run" : null,
        o.sources ? o.sources.join(", ") : "All sources",
        o.max_tailor != null ? `max ${o.max_tailor} CVs` : null,
      ];
      return <span className="text-caption text-muted-foreground">{parts.filter(Boolean).join(" · ")}</span>;
    },
  },
];

export default function RunsPage() {
  const navigate = useNavigate();
  const startRun = useStartRun();
  const runs = useRunsList(200);

  return (
    <>
      <PageHeader
        title="Runs"
        description="Every time the agent searched, filtered and tailored. Open a run for its full log."
        actions={
          <Button onClick={startRun} disabled={Boolean(runs.data?.active_id)}>
            <Play /> Start run
          </Button>
        }
      />
      {runs.isPending && <SkeletonRows rows={8} />}
      {runs.isError && <ErrorState error={runs.error} onRetry={() => runs.refetch()} />}
      {runs.data && runs.data.items.length === 0 && (
        <EmptyState
          icon={History}
          title="No runs yet"
          description="Start a run to search Adzuna, Arbeitnow and your Gmail alerts. It usually takes a few minutes."
          action={
            <Button onClick={startRun}>
              <Play /> Start your first run
            </Button>
          }
        />
      )}
      {runs.data && runs.data.items.length > 0 && (
        <DataTable
          caption="Run history"
          data={runs.data.items}
          columns={columns}
          getRowId={(run) => String(run.id)}
          onRowClick={(run) => navigate(`/runs/${run.id}`)}
        />
      )}
    </>
  );
}
