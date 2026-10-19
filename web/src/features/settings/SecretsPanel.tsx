import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, KeyRound, PlugZap } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { useConfirm } from "@/components/confirm";
import { ErrorState, SkeletonForm } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/controls";
import { Badge, Card, Input } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { SecretField, SettingsResponse } from "@/lib/types";

const GROUPS: { id: string; title: string; description: string; help?: { href: string; label: string } }[] = [
  {
    id: "groq",
    title: "Groq",
    description: "Writes the tailored summary and bullets, and reads resume files during import.",
    help: { href: "https://console.groq.com/keys", label: "Create a Groq key" },
  },
  {
    id: "adzuna",
    title: "Adzuna",
    description: "Searches Belgian job listings by keyword.",
    help: { href: "https://developer.adzuna.com/signup", label: "Get Adzuna API keys" },
  },
  {
    id: "smtp",
    title: "Email alerts (Gmail SMTP)",
    description:
      "Optional: emails you when a run tailors a CV. Needs a Gmail app password, not your normal password.",
    help: { href: "https://myaccount.google.com/apppasswords", label: "Create an app password" },
  },
];

function SecretRow({ field }: { field: SecretField }) {
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
        description: "Stored in .env on this computer.",
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
                    description: "It is deleted from .env.",
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
        <PlugZap /> {name === "smtp" ? "Send test email" : "Test connection"}
      </Button>
      {test.data && (
        <span className={test.data.ok ? "text-body text-success" : "text-body text-danger"} role="status">
          {test.data.message}
        </span>
      )}
    </div>
  );
}

function SmtpToggle() {
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: keys.settings,
    queryFn: () => api.get<SettingsResponse>("/api/settings/search"),
  });
  const save = useMutation({
    mutationFn: (enabled: boolean) =>
      api.put<SettingsResponse>("/api/settings/search", {
        settings: { ...settings.data!.settings, alerts: { smtp_enabled: enabled } },
      }),
    onSuccess: (result, enabled) => {
      queryClient.setQueryData(keys.settings, result);
      queryClient.invalidateQueries({ queryKey: keys.integrations });
      toast.success(enabled ? "Email alerts turned on" : "Email alerts turned off");
    },
    onError: (error: Error) => toast.error("The setting was not saved", { description: error.message }),
  });
  return (
    <label className="flex items-center gap-3 text-body">
      <Switch
        checked={Boolean(settings.data?.settings.alerts.smtp_enabled)}
        disabled={!settings.data || save.isPending}
        onCheckedChange={(enabled) => save.mutate(enabled)}
      />
      Send email alerts
    </label>
  );
}

export function SecretsPanel({ groups = ["groq", "adzuna", "smtp"] }: { groups?: string[] }) {
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
          {group.id === "smtp" && <SmtpToggle />}
          {secrets.data
            .filter((field) => field.group === group.id)
            .map((field) => (
              <SecretRow key={field.key} field={field} />
            ))}
          <TestButton name={group.id} />
        </Card>
      ))}
      <p className="text-caption text-muted-foreground">
        Keys are saved in <span className="font-mono">.env</span> next to the app and never shown in full
        again.
      </p>
    </div>
  );
}
