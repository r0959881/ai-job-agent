import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, KeyRound, PlugZap } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { useConfirm } from "@/components/confirm";
import { ErrorState, SkeletonForm } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Badge, Card, Input } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import { useSession } from "@/lib/session";
import type { SecretField } from "@/lib/types";

const GROUPS: { id: string; title: string; description: string; help?: { href: string; label: string } }[] = [
  {
    id: "groq",
    title: "Groq",
    description:
      "Writes the tailored summary and bullets, and reads resume files during import. Add a second key as a backup: it takes over when the first one reaches Groq's limit.",
    help: { href: "https://console.groq.com/keys", label: "Create a Groq key" },
  },
  {
    id: "adzuna",
    title: "Adzuna (optional)",
    description: "A job search API for 19 countries. Free keys; runs skip Adzuna without them.",
    help: { href: "https://developer.adzuna.com/signup", label: "Get Adzuna API keys" },
  },
  {
    id: "brave",
    title: "Brave Search (optional)",
    description:
      "Powers the Web search source. When its quota runs out, web search falls back to Groq (at most 2 searches per run).",
    help: { href: "https://api-dashboard.search.brave.com/app/keys", label: "Get a Brave Search key" },
  },
];

function SecretRow({ field }: { field: SecretField }) {
  const projectFiles = Boolean(useSession().data?.project_files);
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState("");
  const [visible, setVisible] = React.useState(false);
  const save = useMutation({
    mutationFn: (next: string) =>
      api.put<SecretField[]>("/api/settings/secrets", { values: { [field.key]: next } }),
    onSuccess: (fields, next) => {
      queryClient.setQueryData(keys.secrets, fields);
      queryClient.invalidateQueries({ queryKey: keys.integrations });
      queryClient.invalidateQueries({ queryKey: keys.stats });
      toast.success(next ? `${field.label} saved` : `${field.label} removed`, {
        description: projectFiles
          ? "Saved in the project's .env file."
          : "Saved, encrypted, in your account.",
      });
      setEditing(false);
      setValue("");
    },
    onError: (error: Error) => toast.error(`${field.label} was not saved`, { description: error.message }),
  });
  const id = `secret-${field.key}`;
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={id} className="text-body font-medium">
          {field.label}
        </label>
        <span className="font-mono text-caption text-muted-foreground">{field.key}</span>
        {field.set ? (
          <Badge variant="success">Set · {field.masked}</Badge>
        ) : (
          <Badge variant="outline">Not set</Badge>
        )}
      </div>
      {editing ? (
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (value.trim()) save.mutate(value.trim());
          }}
        >
          <div className="relative flex-1">
            <Input
              id={id}
              autoFocus
              autoComplete="off"
              spellCheck={false}
              type={visible ? "text" : "password"}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={field.set ? "Paste the new value" : "Paste the value"}
              className="pr-10 font-mono"
            />
            <button
              type="button"
              className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
              onClick={() => setVisible((v) => !v)}
              aria-label={visible ? "Hide value" : "Show value"}
            >
              {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
          <Button type="submit" loading={save.isPending} disabled={!value.trim()}>
            Save
          </Button>
          <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </form>
      ) : (
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            <KeyRound /> {field.set ? "Replace" : "Add"}
          </Button>
          {field.set && (
            <Button
              size="sm"
              variant="ghost"
              onClick={async () => {
                if (
                  await confirm({
                    title: `Remove ${field.label}?`,
                    description: "It is deleted from your account.",
                    confirmLabel: "Remove",
                    destructive: true,
                  })
                )
                  save.mutate("");
              }}
            >
              Remove
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function TestButton({ name }: { name: string }) {
  const test = useMutation({
    mutationFn: () => api.post<{ ok: boolean; message: string }>(`/api/integrations/${name}/test`),
    onSuccess: (result) => (result.ok ? toast.success : toast.error)(result.message),
    onError: (error: Error) => toast.error("The test could not run", { description: error.message }),
  });
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" variant="secondary" onClick={() => test.mutate()} loading={test.isPending}>
        <PlugZap /> Test connection
      </Button>
      {test.data && (
        <span className={test.data.ok ? "text-body text-success" : "text-body text-danger"} role="status">
          {test.data.message}
        </span>
      )}
    </div>
  );
}

export function SecretsPanel({ groups = ["groq", "adzuna", "brave"] }: { groups?: string[] }) {
  const projectFiles = Boolean(useSession().data?.project_files);
  const secrets = useQuery({
    queryKey: keys.secrets,
    queryFn: () => api.get<SecretField[]>("/api/settings/secrets"),
  });
  if (secrets.isPending) return <SkeletonForm fields={4} />;
  if (secrets.isError) return <ErrorState error={secrets.error} onRetry={() => secrets.refetch()} />;
  return (
    <div className="space-y-4">
      {GROUPS.filter((group) => groups.includes(group.id)).map((group) => (
        <Card key={group.id} className="space-y-4 p-4">
          <div className="space-y-0.5">
            <h3 className="text-section">{group.title}</h3>
            <p className="max-w-prose text-body text-muted-foreground">
              {group.description}{" "}
              {group.help && (
                <a
                  className="text-primary underline underline-offset-4 hover:decoration-2"
                  href={group.help.href}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {group.help.label}
                </a>
              )}
            </p>
          </div>
          {secrets.data
            .filter((field) => field.group === group.id)
            .map((field) => (
              <SecretRow key={field.key} field={field} />
            ))}
          <TestButton name={group.id} />
        </Card>
      ))}
      <p className="text-caption text-muted-foreground">
        {projectFiles
          ? "This account uses the project's own files: keys are read from and saved to .env, the same file the command line uses. They are never shown in full again."
          : "Keys are encrypted in your account on the server and never shown in full again. Only your own runs use them."}
      </p>
    </div>
  );
}
