import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FolderCheck, FolderOpen, FolderSync, HardDrive, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import * as folder from "@/lib/local/folder";
import { downloadBlob } from "@/lib/local/routes";
import * as store from "@/lib/local/store";
import { cn } from "@/lib/utils";

export const folderKey = ["folder"] as const;

export function useFolderState() {
  return useQuery({ queryKey: folderKey, queryFn: folder.folderState, staleTime: 30_000 });
}

/** After a folder is connected: load its data file, move browser-only files in, and index what is there. */
async function adopt() {
  const imported = await store.importDataFile();
  const moved = await store.moveBrowserFilesToFolder();
  const scanned = await store.rescanFolder();
  await store.writeDataFile();
  return { ...imported, moved, found: scanned.added };
}

export function useFolderActions() {
  const queryClient = useQueryClient();
  const done = (result: Awaited<ReturnType<typeof adopt>> | null, verb: string) => {
    queryClient.invalidateQueries({ queryKey: folderKey });
    if (!result) return;
    const parts = [
      result.jobs && `${result.jobs} job(s) restored`,
      result.moved && `${result.moved} file(s) moved in`,
      result.found && `${result.found} existing file(s) found`,
    ].filter(Boolean);
    toast.success(`Folder ${verb}`, {
      description: parts.join(", ") || "New CVs and reports are saved there.",
    });
  };
  const pick = useMutation({
    mutationFn: async () => ((await folder.pickFolder()) ? adopt() : null),
    onSuccess: (result) => done(result, "connected"),
    onError: (error: Error) => toast.error("The folder could not be used", { description: error.message }),
  });
  const reconnect = useMutation({
    mutationFn: async () => ((await folder.reconnectFolder()) ? adopt() : null),
    onSuccess: (result) => done(result, "reconnected"),
    onError: (error: Error) => toast.error("Access was not granted", { description: error.message }),
  });
  return { pick, reconnect };
}

/** A compact notice for pages that save files, shown when the folder is missing or needs a click. */
export function FolderNotice({ className }: { className?: string }) {
  const state = useFolderState();
  const { pick, reconnect } = useFolderActions();
  if (!state.data || state.data.status === "ready" || state.data.status === "project") return null;
  const status = state.data.status;
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-md bg-warning-soft p-3 text-body text-warning",
        className,
      )}
    >
      <TriangleAlert className="size-4 shrink-0" aria-hidden />
      <span className="flex-1">
        {status === "needs-permission"
          ? `Allow access to “${state.data.name}” again so new CVs are saved there.`
          : status === "none"
            ? "Choose a folder on your computer for CVs, cover letters and reports."
            : "This browser cannot save into a folder, so files are kept in browser storage. Use Chrome or Edge to save them into a folder."}
      </span>
      {status === "needs-permission" && (
        <Button size="sm" variant="outline" loading={reconnect.isPending} onClick={() => reconnect.mutate()}>
          <FolderSync /> Allow access
        </Button>
      )}
      {status === "none" && (
        <Button size="sm" variant="outline" loading={pick.isPending} onClick={() => pick.mutate()}>
          <FolderOpen /> Choose folder
        </Button>
      )}
    </div>
  );
}

export function StorageCard() {
  const queryClient = useQueryClient();
  const state = useFolderState();
  const { pick, reconnect } = useFolderActions();
  const exportData = useMutation({
    mutationFn: async () => {
      const data = await store.exportData();
      downloadBlob(new Blob([JSON.stringify(data, null, 1)], { type: "application/json" }), folder.DATA_FILE);
    },
  });
  const forget = useMutation({
    mutationFn: folder.forgetFolder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: folderKey });
      toast.success("Folder disconnected", { description: "Files already in it stay where they are." });
    },
  });
  const status = state.data?.status;
  if (status === "project") {
    return (
      <Card className="space-y-2 p-4">
        <div className="flex items-start gap-3">
          <FolderCheck className="mt-0.5 size-5 text-success" aria-hidden />
          <div className="flex-1 space-y-1">
            <h3 className="text-section">Documents folder: the project&apos;s output folder</h3>
            <p className="max-w-prose text-body text-muted-foreground">
              You are using the local account on this PC. CVs, cover letters and reports are saved in the
              project&apos;s <span className="font-mono">output</span> folder, the same one the command line
              uses, and the jobs from <span className="font-mono">jobs.db</span> are shown here. Your profile,
              settings and API keys are the project&apos;s <span className="font-mono">resume_data.yaml</span>
              , <span className="font-mono">agent_settings.yaml</span> and{" "}
              <span className="font-mono">.env</span>.
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={() => exportData.mutate()} loading={exportData.isPending}>
          <Download /> Download job list
        </Button>
      </Card>
    );
  }
  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-start gap-3">
        {status === "ready" ? (
          <FolderCheck className="mt-0.5 size-5 text-success" aria-hidden />
        ) : (
          <HardDrive className="mt-0.5 size-5 text-muted-foreground" aria-hidden />
        )}
        <div className="flex-1 space-y-1">
          <h3 className="text-section">Documents folder</h3>
          <p className="max-w-prose text-body text-muted-foreground">
            CVs, cover letters and reports are saved on this computer, never on the server. In the folder you
            choose they go into <span className="font-mono">CVs</span>,{" "}
            <span className="font-mono">Cover letters</span> and <span className="font-mono">Reports</span>,
            next to <span className="font-mono">{folder.DATA_FILE}</span> with your job list.
          </p>
          <p className="text-body">
            {status === "ready" && (
              <>
                Saving to <strong>{state.data?.status === "ready" && state.data.name}</strong>.
              </>
            )}
            {status === "needs-permission" && (
              <>
                The browser needs your permission again for{" "}
                <strong>{state.data?.status === "needs-permission" && state.data.name}</strong>.
              </>
            )}
            {status === "none" &&
              "No folder chosen yet. Until you choose one, files are kept in this browser."}
            {status === "unsupported" &&
              "This browser cannot save into a folder (Chrome and Edge can). Files are kept in browser storage; download them from the Documents page."}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {status !== "unsupported" && (
          <Button onClick={() => pick.mutate()} loading={pick.isPending}>
            <FolderOpen />{" "}
            {status === "ready" || status === "needs-permission" ? "Choose another folder" : "Choose folder"}
          </Button>
        )}
        {status === "needs-permission" && (
          <Button variant="outline" onClick={() => reconnect.mutate()} loading={reconnect.isPending}>
            <FolderSync /> Allow access again
          </Button>
        )}
        {(status === "ready" || status === "needs-permission") && (
          <Button variant="ghost" onClick={() => forget.mutate()} loading={forget.isPending}>
            Disconnect
          </Button>
        )}
        <Button variant="outline" onClick={() => exportData.mutate()} loading={exportData.isPending}>
          <Download /> Download job list
        </Button>
      </div>
      <p className="text-caption text-muted-foreground">
        Opening the app in another browser? Choose the same folder there and your jobs are restored from{" "}
        <span className="font-mono">{folder.DATA_FILE}</span>.
      </p>
    </Card>
  );
}
