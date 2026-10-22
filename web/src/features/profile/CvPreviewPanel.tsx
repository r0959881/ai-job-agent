import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import * as React from "react";
import { ErrorState, SkeletonRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/controls";
import { Card } from "@/components/ui/primitives";
import { PdfFrame } from "@/features/documents/PdfFrame";
import { api } from "@/lib/api";
import type { Resume } from "@/lib/types";

/** Renders a sample CV from the current (possibly unsaved) form data. */
export function CvPreviewPanel({
  data,
  valid,
  roleFamilies,
  onClose,
}: {
  data: Resume;
  valid: boolean;
  roleFamilies: string[];
  onClose: () => void;
}) {
  const [role, setRole] = React.useState(roleFamilies[0] ?? "");
  const [debounced, setDebounced] = React.useState(data);
  React.useEffect(() => {
    if (!valid) return;
    const timer = window.setTimeout(() => setDebounced(data), 700);
    return () => window.clearTimeout(timer);
  }, [data, valid]);

  const preview = useQuery({
    queryKey: ["resume-preview", role, debounced],
    queryFn: () =>
      api.post<{ pdf: string }>("/api/resume/preview", { data: debounced, role_family: role || null }),
    placeholderData: (previous) => previous,
    staleTime: Infinity,
  });

  return (
    <Card className="sticky top-20 flex max-h-[calc(100vh-6rem)] flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b p-3">
        <h2 className="text-section">CV preview</h2>
        <div className="ml-auto w-48">
          <Select
            aria-label="Role family for the preview"
            value={role}
            onValueChange={setRole}
            options={roleFamilies.map((r) => ({ value: r, label: r }))}
            placeholder="All skills"
          />
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close preview">
          <X />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto bg-muted/40 p-4">
        {!valid && (
          <p className="mb-3 rounded-md bg-warning-soft p-2 text-caption text-warning">
            Fix the highlighted fields to refresh the preview.
          </p>
        )}
        {preview.isPending && <SkeletonRows rows={10} />}
        {preview.isError && <ErrorState error={preview.error} onRetry={() => preview.refetch()} />}
        {preview.data && (
          <div aria-busy={preview.isFetching}>
            <PdfFrame
              base64={preview.data.pdf}
              title="CV preview"
              className="h-[calc(100vh-14rem)] min-h-[480px] w-full rounded-md border bg-card"
            />
          </div>
        )}
      </div>
    </Card>
  );
}
