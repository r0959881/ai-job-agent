import { yaml } from "@codemirror/lang-yaml";
import { linter, lintGutter, type Diagnostic } from "@codemirror/lint";
import { EditorView, basicSetup } from "codemirror";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Save, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { ErrorState, SkeletonRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { YamlError } from "@/lib/types";

const editorTheme = EditorView.theme({
  "&": { backgroundColor: "hsl(var(--background))", color: "hsl(var(--foreground))", height: "100%" },
  ".cm-content": {
    caretColor: "hsl(var(--foreground))",
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
  },
  ".cm-gutters": {
    backgroundColor: "hsl(var(--muted))",
    color: "hsl(var(--muted-foreground))",
    borderRight: "1px solid hsl(var(--border))",
  },
  ".cm-activeLine": { backgroundColor: "hsl(var(--accent) / 0.5)" },
  ".cm-activeLineGutter": { backgroundColor: "hsl(var(--accent))" },
  "&.cm-focused .cm-cursor": { borderLeftColor: "hsl(var(--foreground))" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "hsl(var(--primary) / 0.25)",
  },
  ".cm-tooltip": { backgroundColor: "hsl(var(--popover))", color: "hsl(var(--popover-foreground))" },
});

export function YamlEditor({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const raw = useQuery({
    queryKey: keys.resumeRaw,
    queryFn: () => api.get<{ text: string; etag: string }>("/api/resume/raw"),
    gcTime: 0,
  });
  const host = React.useRef<HTMLDivElement>(null);
  const view = React.useRef<EditorView | null>(null);
  const [errors, setErrors] = React.useState<YamlError[]>([]);
  const [dirty, setDirty] = React.useState(false);

  React.useEffect(() => {
    if (!raw.data || !host.current || view.current) return;
    const yamlLinter = linter(
      async (editor) => {
        const result = await api
          .post<{
            valid: boolean;
            errors: YamlError[];
          }>("/api/resume/raw/validate", { text: editor.state.doc.toString() })
          .catch(() => ({ valid: true, errors: [] as YamlError[] }));
        setErrors(result.errors);
        return result.errors.map((error): Diagnostic => {
          const lineNumber = Math.min(Math.max(error.line ?? 1, 1), editor.state.doc.lines);
          const line = editor.state.doc.line(lineNumber);
          return { from: line.from, to: line.to, severity: "error", message: error.message };
        });
      },
      { delay: 600 },
    );
    view.current = new EditorView({
      doc: raw.data.text,
      parent: host.current,
      extensions: [
        basicSetup,
        yaml(),
        lintGutter(),
        yamlLinter,
        editorTheme,
        EditorView.lineWrapping,
        EditorView.contentAttributes.of({ "aria-label": "resume_data.yaml" }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) setDirty(true);
        }),
      ],
    });
    return () => {
      view.current?.destroy();
      view.current = null;
    };
  }, [raw.data]);

  const save = useMutation({
    mutationFn: () =>
      api.put<{ etag: string; backup_id: string | null }>("/api/resume/raw", {
        text: view.current?.state.doc.toString() ?? "",
        etag: raw.data?.etag,
      }),
    onSuccess: (result) => {
      toast.success("resume_data.yaml saved", {
        description: result.backup_id ? "The previous version is in History." : "No changes to save.",
      });
      setDirty(false);
      queryClient.invalidateQueries({ queryKey: keys.resume });
      queryClient.invalidateQueries({ queryKey: keys.backups });
      onClose();
    },
    onError: (error: Error) => toast.error("The YAML was not saved", { description: error.message }),
  });

  if (raw.isPending) return <SkeletonRows rows={12} />;
  if (raw.isError) return <ErrorState error={raw.error} onRetry={() => raw.refetch()} />;

  return (
    <Card className="flex h-[calc(100vh-12rem)] min-h-[420px] flex-col overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b p-3">
        <p className="flex-1 text-body text-muted-foreground">
          Editing <span className="font-mono">resume_data.yaml</span> directly. Comments and formatting are
          kept.
        </p>
        {errors.length ? (
          <span className="flex items-center gap-1 text-body text-danger" role="status">
            <AlertTriangle className="size-4" /> {errors.length} problem{errors.length === 1 ? "" : "s"}
          </span>
        ) : (
          <span className="flex items-center gap-1 text-body text-success" role="status">
            <CheckCircle2 className="size-4" /> Valid
          </span>
        )}
        <Button variant="outline" size="sm" onClick={onClose}>
          <X /> Back to the form
        </Button>
        <Button
          size="sm"
          onClick={() => save.mutate()}
          loading={save.isPending}
          disabled={!dirty || errors.length > 0}
        >
          <Save /> Save YAML
        </Button>
      </div>
      <div ref={host} className="min-h-0 flex-1 overflow-auto" />
      {errors.length > 0 && (
        <ul className="max-h-32 overflow-y-auto border-t bg-danger-soft p-3 text-body text-danger">
          {errors.map((error, index) => (
            <li key={index}>
              {error.line ? `Line ${error.line}: ` : ""}
              {error.message}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
