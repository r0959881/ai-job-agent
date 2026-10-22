import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DocumentDownload } from "@/features/documents/DocumentDownload";
import { PdfFrame } from "@/features/documents/PdfFrame";
import { Download, ExternalLink, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useConfirm } from "@/components/confirm";
import { ErrorState, SkeletonRows } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/overlays";
import { api } from "@/lib/api";
import type { DocumentItem } from "@/lib/types";

const KIND_LABEL: Record<string, string> = {
  cv: "Tailored CV",
  cover_letter: "Cover letter",
  report: "Excel report",
  other: "File",
};

/** "Consultant Data Engineer_Sia_CL.docx" -> "Consultant Data Engineer · Sia". The file name carries the
 *  cleaned title, where job alerts store theirs as "Consultant Data EngineerSia · Antwerp (Hybrid)Easy Apply". */
function headline(document: DocumentItem) {
  const match = document.name.match(/^(.+)_(?:CV|CL)\.[a-z]+$/i);
  return match ? match[1].replace(/_/g, " · ") : document.job_title;
}

export function useDocumentActions() {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: ["jobs"] });
    queryClient.invalidateQueries({ queryKey: ["job"] });
    queryClient.invalidateQueries({ queryKey: ["stats"] });
    queryClient.invalidateQueries({ queryKey: ["runs"] });
  };
  const remove = useMutation({
    mutationFn: (doc: DocumentItem) => api.delete(`/api/documents/${doc.id}`),
    onSuccess: (_result, doc) => {
      toast.success(`Deleted ${doc.name}`);
      invalidate();
    },
    onError: (error: Error) => toast.error("The file was not deleted", { description: error.message }),
  });
  const regenerate = useMutation({
    mutationFn: (doc: DocumentItem) => api.post(`/api/documents/${doc.id}/regenerate`),
    onSuccess: (_result, doc) => {
      toast.success(`${KIND_LABEL[doc.kind]} regenerated`);
      invalidate();
    },
    onError: (error: Error) => toast.error("Regeneration failed", { description: error.message }),
  });
  const open = useMutation({
    mutationFn: (doc: DocumentItem) => api.post(`/api/documents/${doc.id}/open`),
    onSuccess: (_result, doc) =>
      toast.success(`Downloaded ${doc.name}`, {
        description: "Open it from your browser's downloads to edit it in Word.",
      }),
    onError: (error: Error) => toast.error("Could not open the file", { description: error.message }),
  });
  const confirmDelete = async (doc: DocumentItem) => {
    const ok = await confirm({
      title: `Delete ${KIND_LABEL[doc.kind].toLowerCase()}?`,
      description: (
        <>
          <p className="break-all font-mono text-caption">{doc.name}</p>
          <p className="mt-2">The file is permanently removed from your documents folder.</p>
        </>
      ),
      confirmLabel: "Delete file",
      destructive: true,
    });
    if (ok) await remove.mutateAsync(doc);
    return ok;
  };
  return { remove, regenerate, open, confirmDelete };
}

export function DocumentPreviewDialog({
  document,
  onOpenChange,
}: {
  document: DocumentItem | null;
  onOpenChange: (open: boolean) => void;
}) {
  const actions = useDocumentActions();
  const preview = useQuery({
    queryKey: ["document-preview", document?.id, document?.created_at],
    queryFn: () => api.get<{ html?: string; pdf?: File }>(`/api/documents/${document!.id}/preview`),
    enabled: Boolean(document) && document?.kind !== "report",
  });
  const canRegenerate =
    document &&
    (document.kind === "cv" || document.kind === "cover_letter") &&
    (document.job_id || document.role_family);

  return (
    <Dialog open={Boolean(document)} onOpenChange={onOpenChange}>
      <DialogContent wide className="flex max-h-[92vh] flex-col">
        {document && (
          <>
            <DialogHeader>
              <DialogTitle>
                {headline(document)
                  ? `${KIND_LABEL[document.kind]}: ${headline(document)}`
                  : KIND_LABEL[document.kind]}
              </DialogTitle>
              <DialogDescription className="break-all">{document.name}</DialogDescription>
            </DialogHeader>
            <div className="flex flex-wrap gap-2">
              <DocumentDownload className={buttonVariants({ size: "sm" })} id={document.id}>
                <Download /> Download
              </DocumentDownload>
              <Button
                size="sm"
                variant="outline"
                onClick={() => actions.open.mutate(document)}
                loading={actions.open.isPending}
              >
                <ExternalLink /> Open
              </Button>
              {canRegenerate && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => actions.regenerate.mutate(document)}
                  loading={actions.regenerate.isPending}
                >
                  <RefreshCw /> Regenerate
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                className="text-danger hover:text-danger"
                onClick={async () => {
                  if (await actions.confirmDelete(document)) onOpenChange(false);
                }}
              >
                <Trash2 /> Delete
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto rounded-md border bg-muted/40 p-4">
              {document.kind === "report" ? (
                <p className="text-body text-muted-foreground">
                  Excel reports cannot be previewed here. Download or open it in Excel.
                </p>
              ) : preview.isPending ? (
                <SkeletonRows rows={10} />
              ) : preview.isError ? (
                <ErrorState error={preview.error} onRetry={() => preview.refetch()} />
              ) : preview.data.pdf ? (
                <PdfFrame blob={preview.data.pdf} title={document.name} />
              ) : (
                <div
                  className="doc-preview rounded-md bg-card p-6 text-card-foreground shadow-card"
                  dangerouslySetInnerHTML={{ __html: preview.data.html ?? "" }}
                />
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
