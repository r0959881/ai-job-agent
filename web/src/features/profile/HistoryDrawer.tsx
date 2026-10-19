import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, RotateCcw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { RelativeTime } from "@/components/common";
import { useConfirm } from "@/components/confirm";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/overlays";
import { api } from "@/lib/api";
import { diffLines, withContext } from "@/lib/diff";
import { keys } from "@/lib/queries";
import type { BackupInfo } from "@/lib/types";
import { cn, formatAbsolute } from "@/lib/utils";

export function HistoryDrawer({
  open,
  onOpenChange,
  dirty,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dirty: boolean;
}) {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [selected, setSelected] = React.useState<string | null>(null);
  const backups = useQuery({
    queryKey: keys.backups,
    queryFn: () => api.get<BackupInfo[]>("/api/resume/backups"),
    enabled: open,
  });
  const current = useQuery({
    queryKey: keys.resumeRaw,
    queryFn: () => api.get<{ text: string }>("/api/resume/raw"),
    enabled: open,
  });
  const backup = useQuery({
    queryKey: ["resume", "backup", selected],
    queryFn: () => api.get<{ text: string }>(`/api/resume/backups/${selected}`),
    enabled: open && Boolean(selected),
  });

  React.useEffect(() => {
    if (open && !selected && backups.data?.length) setSelected(backups.data[0].id);
  }, [open, selected, backups.data]);

  const restore = useMutation({
    mutationFn: (id: string) => api.post(`/api/resume/backups/${id}/restore`),
    onSuccess: () => {
      toast.success("Backup restored", { description: "The version you replaced was backed up first." });
      queryClient.invalidateQueries({ queryKey: keys.resume });
      onOpenChange(false);
    },
    onError: (error: Error) => toast.error("Could not restore the backup", { description: error.message }),
  });

  const diff = React.useMemo(() => {
    if (!backup.data || !current.data) return null;
    return withContext(diffLines(backup.data.text, current.data.text));
  }, [backup.data, current.data]);
  const changes = diff?.filter((line) => line.type === "add" || line.type === "remove").length ?? 0;

  const onRestore = async (item: BackupInfo) => {
    const ok = await confirm({
      title: "Restore this version?",
      description: (
        <>
          <p>Your resume will be replaced with the version from {formatAbsolute(item.created_at)}.</p>
          {dirty && (
            <p className="mt-2 font-medium text-warning">Your unsaved edits in the form will be lost.</p>
          )}
        </>
      ),
      confirmLabel: "Restore",
    });
    if (ok) restore.mutate(item.id);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="max-w-4xl">
        <div className="border-b p-4 pr-12">
          <SheetTitle>History</SheetTitle>
          <SheetDescription>
            The last 20 versions of resume_data.yaml. A copy is kept before every save.
          </SheetDescription>
        </div>
        <div className="grid min-h-0 flex-1 md:grid-cols-[16rem_1fr]">
          <div className="overflow-y-auto border-b p-2 md:border-b-0 md:border-r">
            {backups.isPending && <SkeletonRows rows={5} />}
            {backups.isError && <ErrorState error={backups.error} onRetry={() => backups.refetch()} />}
            {backups.data?.length === 0 && (
              <EmptyState
                icon={History}
                title="No backups yet"
                description="Save your profile once to start a history."
              />
            )}
            <ul className="space-y-1">
              {backups.data?.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(item.id)}
                    className={cn(
                      "w-full rounded-md px-3 py-2 text-left hover:bg-muted",
                      selected === item.id && "bg-accent text-accent-foreground hover:bg-accent",
                    )}
                    aria-current={selected === item.id}
                  >
                    <RelativeTime value={item.created_at} className="font-medium" />
                    <span className="block text-caption text-muted-foreground">{item.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="flex min-h-0 flex-col">
            {selected && backups.data && (
              <div className="flex items-center justify-between gap-2 border-b p-3">
                <p className="text-body text-muted-foreground">
                  {changes === 0
                    ? "Identical to the current version."
                    : `${changes} changed line(s) since this version.`}{" "}
                  <span className="text-success">+ now</span> / <span className="text-danger">− backup</span>
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  loading={restore.isPending}
                  onClick={() => {
                    const item = backups.data.find((b) => b.id === selected);
                    if (item) onRestore(item);
                  }}
                >
                  <RotateCcw /> Restore
                </Button>
              </div>
            )}
            <div className="min-h-0 flex-1 overflow-auto p-2 font-mono text-[12px] leading-5">
              {backup.isPending && selected && <SkeletonRows rows={10} />}
              {diff?.map((line, index) =>
                line.type === "gap" ? (
                  <div key={index} className="px-2 py-1 text-muted-foreground">
                    ⋯ {line.count} unchanged line{line.count === 1 ? "" : "s"}
                  </div>
                ) : (
                  <div
                    key={index}
                    className={cn(
                      "whitespace-pre-wrap break-all px-2",
                      line.type === "add" && "bg-success-soft text-success",
                      line.type === "remove" && "bg-danger-soft text-danger",
                    )}
                  >
                    <span aria-hidden className="mr-2 select-none">
                      {line.type === "add" ? "+" : line.type === "remove" ? "−" : " "}
                    </span>
                    <span className="sr-only">
                      {line.type === "add" ? "Added: " : line.type === "remove" ? "Removed: " : ""}
                    </span>
                    {line.text}
                  </div>
                ),
              )}
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
