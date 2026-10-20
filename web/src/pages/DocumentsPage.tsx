import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DocumentDownload } from "@/features/documents/DocumentDownload";
import {
  Download,
  Eye,
  FileSpreadsheet,
  FileText,
  FolderSearch,
  LayoutGrid,
  List,
  Mail,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader, RelativeTime } from "@/components/common";
import { useConfirm } from "@/components/confirm";
import { EmptyState, ErrorState, SkeletonCards } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox, Select } from "@/components/ui/controls";
import { Badge, Card, Input } from "@/components/ui/primitives";
import { DocumentPreviewDialog } from "@/features/documents/DocumentPreviewDialog";
import { api } from "@/lib/api";
import type { DocumentItem } from "@/lib/types";
import { cn } from "@/lib/utils";

const KINDS = [
  { value: "all", label: "All types" },
  { value: "cv", label: "CVs" },
  { value: "cover_letter", label: "Cover letters" },
  { value: "report", label: "Excel reports" },
  { value: "other", label: "Other files" },
];
const KIND_LABEL: Record<string, string> = {
  cv: "CV",
  cover_letter: "Cover letter",
  report: "Report",
  other: "File",
};
const SINCE = [
  { value: "all", label: "Any date" },
  { value: "1", label: "Last 24 hours" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
];

function KindIcon({ kind }: { kind: string }) {
  if (kind === "report") return <FileSpreadsheet className="size-5 text-success" aria-hidden />;
  if (kind === "cover_letter") return <Mail className="size-5 text-info" aria-hidden />;
  return <FileText className="size-5 text-primary" aria-hidden />;
}

/** "Ammar_Haider_CV_Acme_Junior Data Engineer.docx" -> "Acme · Junior Data Engineer" */
export function prettyName(name: string) {
  const stem = name.replace(/\.[^.]+$/, "");
  const match = stem.match(/_(?:CV|Cover_Letter)_(.*)$/);
  return (match ? match[1] : stem).replace(/_/g, " · ").replace(/\s+/g, " ").trim();
}

const isOrphan = (doc: DocumentItem) => doc.kind !== "report" && !doc.job_title;

export default function DocumentsPage() {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "all";
  const orphans = params.get("orphans") === "1";
  const roleFamily = params.get("role") ?? "all";
  const since = params.get("since") ?? "all";
  const view = (params.get("view") ?? "list") as "list" | "grid";
  const group = (params.get("group") ?? "type") as "type" | "job";
  const [q, setQ] = React.useState("");
  const [preview, setPreview] = React.useState<DocumentItem | null>(null);
  const [selected, setSelected] = React.useState<Set<number>>(new Set());

  const setParam = (key: string, value: string, fallback: string) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value === fallback) next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );

  const docs = useQuery({
    queryKey: ["documents", "all"],
    queryFn: () => api.get<{ items: DocumentItem[] }>("/api/documents"),
  });
  const rescan = useMutation({
    mutationFn: () => api.post<{ added: number; removed: number; linked: number }>("/api/documents/rescan"),
    onSuccess: (result) => {
      toast.success("Documents folder rescanned", {
        description: `${result.added} new, ${result.removed} removed, ${result.linked} linked to jobs.`,
      });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (error: Error) => toast.error("Rescan failed", { description: error.message }),
  });
  const bulkDelete = useMutation({
    mutationFn: (ids: number[]) =>
      api.post<{ deleted: number[]; failed: { id: number; reason: string }[] }>(
        "/api/documents/bulk-delete",
        { ids },
      ),
    onSuccess: (result) => {
      (result.failed.length ? toast.warning : toast.success)(`Deleted ${result.deleted.length} file(s)`, {
        description: result.failed.length
          ? `${result.failed.length} could not be deleted: ${result.failed[0].reason}`
          : undefined,
      });
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => toast.error("Delete failed", { description: error.message }),
  });

  const all = docs.data?.items ?? [];
  const roleFamilies = [...new Set(all.map((d) => d.role_family).filter(Boolean))].sort();
  const cutoff = since === "all" ? null : Date.now() - Number(since) * 86_400_000;
  const needle = q.trim().toLowerCase();
  const filtered = all.filter(
    (doc) =>
      (kind === "all" || doc.kind === kind) &&
      (!orphans || isOrphan(doc)) &&
      (roleFamily === "all" || doc.role_family === roleFamily) &&
      (!cutoff || new Date(doc.created_at).getTime() >= cutoff) &&
      (!needle ||
        `${doc.name} ${doc.job_title ?? ""} ${doc.job_company ?? ""}`.toLowerCase().includes(needle)),
  );
  const orphanCount = all.filter(isOrphan).length;

  const groups = new Map<string, DocumentItem[]>();
  for (const doc of filtered) {
    const key =
      group === "job"
        ? doc.job_title
          ? `${doc.job_title} · ${doc.job_company}`
          : doc.kind === "report"
            ? "Excel reports"
            : "Not linked to a job"
        : (KINDS.find((k) => k.value === doc.kind)?.label ?? "Other files");
    groups.set(key, [...(groups.get(key) ?? []), doc]);
  }

  const toggle = (id: number, on: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const deleteSelected = async () => {
    const ids = [...selected];
    const ok = await confirm({
      title: `Delete ${ids.length} file(s)?`,
      description: "The files are permanently removed from your documents folder.",
      confirmLabel: `Delete ${ids.length} file(s)`,
      destructive: true,
    });
    if (ok) bulkDelete.mutate(ids);
  };

  const DocActions = ({ doc }: { doc: DocumentItem }) =>
    doc.exists ? (
      <div className="flex shrink-0 gap-1">
        {doc.kind !== "report" && (
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={`Preview ${doc.name}`}
            onClick={() => setPreview(doc)}
          >
            <Eye />
          </Button>
        )}
        <DocumentDownload
          className={buttonVariants({ size: "icon-sm", variant: "ghost" })}
          id={doc.id}
          aria-label={`Download ${doc.name}`}
        >
          <Download />
        </DocumentDownload>
      </div>
    ) : (
      <Badge variant="warning">File missing</Badge>
    );

  return (
    <>
      <PageHeader
        title="Documents"
        description="Every tailored CV, cover letter and Excel report, saved on this computer in your documents folder."
        actions={
          <Button variant="outline" onClick={() => rescan.mutate()} loading={rescan.isPending}>
            <RefreshCw /> Rescan folder
          </Button>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search
            className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            aria-label="Search documents"
            placeholder="Search file, job or company…"
            className="pl-8"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="w-40">
          <Select
            aria-label="Type"
            value={kind}
            onValueChange={(v) => setParam("kind", v, "all")}
            options={KINDS}
          />
        </div>
        <div className="w-48">
          <Select
            aria-label="Role family"
            value={roleFamily}
            onValueChange={(v) => setParam("role", v, "all")}
            options={[
              { value: "all", label: "All role families" },
              ...roleFamilies.map((r) => ({ value: r, label: r })),
            ]}
          />
        </div>
        <div className="w-40">
          <Select
            aria-label="Created"
            value={since}
            onValueChange={(v) => setParam("since", v, "all")}
            options={SINCE}
          />
        </div>
        <button
          type="button"
          aria-pressed={orphans}
          onClick={() => setParam("orphans", orphans ? "0" : "1", "0")}
          className={cn(
            "h-9 rounded-full border px-3 text-caption font-medium hover:bg-muted",
            orphans && "border-primary bg-primary text-primary-foreground hover:bg-primary/90",
          )}
        >
          Orphans ({orphanCount})
        </button>
        <div className="ml-auto flex items-center gap-2">
          <div className="w-40">
            <Select
              aria-label="Group by"
              value={group}
              onValueChange={(v) => setParam("group", v, "type")}
              options={[
                { value: "type", label: "Group by type" },
                { value: "job", label: "Group by job" },
              ]}
            />
          </div>
          <div className="flex rounded-md border p-0.5" role="group" aria-label="View">
            <Button
              size="icon-sm"
              variant={view === "list" ? "secondary" : "ghost"}
              aria-pressed={view === "list"}
              aria-label="List view"
              onClick={() => setParam("view", "list", "list")}
            >
              <List />
            </Button>
            <Button
              size="icon-sm"
              variant={view === "grid" ? "secondary" : "ghost"}
              aria-pressed={view === "grid"}
              aria-label="Grid view"
              onClick={() => setParam("view", "grid", "list")}
            >
              <LayoutGrid />
            </Button>
          </div>
        </div>
      </div>

      {(orphans || selected.size > 0) && (
        <div
          className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-accent px-3 py-2"
          role="region"
          aria-label="Bulk actions"
        >
          {orphans && (
            <p className="text-body">
              Orphans are files in output/ that no job points to, such as samples and old test CVs.
            </p>
          )}
          <Button
            size="sm"
            variant="outline"
            className="ml-auto"
            onClick={() => setSelected(new Set(filtered.map((d) => d.id)))}
            disabled={!filtered.length}
          >
            Select all {filtered.length}
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={!selected.size}
            loading={bulkDelete.isPending}
            onClick={deleteSelected}
          >
            <Trash2 /> Delete {selected.size || ""} selected
          </Button>
        </div>
      )}

      {docs.isPending && <SkeletonCards count={8} />}
      {docs.isError && <ErrorState error={docs.error} onRetry={() => docs.refetch()} />}
      {docs.data && filtered.length === 0 && (
        <EmptyState
          icon={FolderSearch}
          title={all.length ? "No documents match" : "No documents yet"}
          description={
            all.length
              ? "Change the filters or search."
              : "Tailored CVs appear here after a run, or generate one from a job's Apply tab."
          }
          action={
            all.length ? undefined : (
              <Link to="/jobs" className={buttonVariants()}>
                Go to jobs
              </Link>
            )
          }
        />
      )}
      <div className="space-y-6">
        {[...groups.entries()].map(([title, items]) => (
          <section key={title} aria-label={title}>
            <h2 className="mb-2 text-section">
              {title}{" "}
              <span className="text-body font-normal text-muted-foreground tabular">({items.length})</span>
            </h2>
            <div
              className={
                view === "grid"
                  ? "grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
                  : "divide-y rounded-lg border"
              }
            >
              {items.map((doc) =>
                view === "grid" ? (
                  <Card
                    key={doc.id}
                    className={cn("flex flex-col gap-3 p-3", selected.has(doc.id) && "ring-2 ring-primary")}
                  >
                    <div className="flex items-start gap-2">
                      <Checkbox
                        aria-label={`Select ${doc.name}`}
                        checked={selected.has(doc.id)}
                        onCheckedChange={(on) => toggle(doc.id, on === true)}
                        className="mt-1"
                      />
                      <KindIcon kind={doc.kind} />
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        onClick={() => doc.kind !== "report" && doc.exists && setPreview(doc)}
                      >
                        <p className="line-clamp-2 break-words font-medium" title={doc.name}>
                          {doc.job_title ?? prettyName(doc.name)}
                        </p>
                        <p className="truncate text-caption text-muted-foreground">
                          {doc.job_company ?? doc.role_family ?? ""}
                        </p>
                      </button>
                    </div>
                    <div className="mt-auto flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-caption text-muted-foreground">
                        <Badge variant="outline">{KIND_LABEL[doc.kind]}</Badge>
                        <RelativeTime value={doc.created_at} className="whitespace-nowrap" />
                      </span>
                      <DocActions doc={doc} />
                    </div>
                  </Card>
                ) : (
                  <div
                    key={doc.id}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2",
                      selected.has(doc.id) && "bg-accent/60",
                    )}
                  >
                    <Checkbox
                      aria-label={`Select ${doc.name}`}
                      checked={selected.has(doc.id)}
                      onCheckedChange={(on) => toggle(doc.id, on === true)}
                    />
                    <KindIcon kind={doc.kind} />
                    <div className="min-w-0 flex-1">
                      {doc.job_id && doc.job_title ? (
                        <Link
                          to={`/jobs/${doc.job_id}`}
                          className="block truncate font-medium hover:underline"
                        >
                          {doc.job_title} · {doc.job_company}
                        </Link>
                      ) : (
                        <p className="truncate font-medium">{prettyName(doc.name)}</p>
                      )}
                      <p className="truncate text-caption text-muted-foreground" title={doc.path}>
                        {doc.name}
                      </p>
                    </div>
                    {doc.role_family && (
                      <Badge variant="secondary" className="hidden md:inline-flex">
                        {doc.role_family}
                      </Badge>
                    )}
                    <RelativeTime
                      value={doc.created_at}
                      className="hidden shrink-0 text-caption text-muted-foreground sm:inline"
                    />
                    <DocActions doc={doc} />
                  </div>
                ),
              )}
            </div>
          </section>
        ))}
      </div>
      <DocumentPreviewDialog document={preview} onOpenChange={(open) => !open && setPreview(null)} />
    </>
  );
}
