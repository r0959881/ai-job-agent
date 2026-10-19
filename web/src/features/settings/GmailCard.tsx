import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleSlash, FileKey2, LogOut, Mail, PlugZap, RefreshCw, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Field, RelativeTime, TagInput } from "@/components/common";
import { useConfirm } from "@/components/confirm";
import { ErrorState, SkeletonForm } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge, Card, Input } from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import { keys, useGmailStatus } from "@/lib/queries";
import type { GmailState, SettingsResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATE: Record<GmailState, { label: string; icon: typeof CheckCircle2; tone: string }> = {
  connected: { label: "Connected", icon: CheckCircle2, tone: "border-success/30 bg-success-soft text-success" },
  reauth_required: { label: "Reconnect required", icon: AlertTriangle, tone: "border-warning/30 bg-warning-soft text-warning" },
  error: { label: "Error", icon: XCircle, tone: "border-danger/30 bg-danger-soft text-danger" },
  not_connected: { label: "Not connected", icon: CircleSlash, tone: "border-border bg-muted text-muted-foreground" },
};

export function startGmailConnect(returnTo = "/settings/integrations") {
  window.location.href = `/api/integrations/gmail/connect?return_to=${encodeURIComponent(returnTo)}`;
}

function SendersEditor() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: keys.settings, queryFn: () => api.get<SettingsResponse>("/api/settings/search") });
  const [senders, setSenders] = React.useState<string[] | null>(null);
  const [days, setDays] = React.useState<number | null>(null);
  const current = settings.data?.settings.gmail;
  const dirty =
    current && ((senders && senders.join() !== current.senders.join()) || (days != null && days !== current.lookback_days));
  const save = useMutation({
    mutationFn: () =>
      api.put<SettingsResponse>("/api/settings/search", {
        settings: {
          ...settings.data!.settings,
          gmail: { ...current!, senders: senders ?? current!.senders, lookback_days: days ?? current!.lookback_days },
        },
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(keys.settings, result);
      setSenders(null);
      setDays(null);
      toast.success("Gmail search updated", { description: "The next run and test use the new senders." });
    },
    onError: (error: Error) => toast.error("Not saved", { description: error.message }),
  });
  if (!current) return null;
  return (
    <div className="space-y-3 border-t pt-4">
      <Field label="Alert senders" htmlFor="gmail-senders" description="Emails from these domains are read as job alerts.">
        <TagInput id="gmail-senders" value={senders ?? current.senders} onChange={setSenders} placeholder="linkedin.com" />
      </Field>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Look back (days)" htmlFor="gmail-days" className="w-40">
          <Input id="gmail-days" type="number" min={1} max={30} className="tabular" value={days ?? current.lookback_days}
            onChange={(e) => setDays(Number(e.target.value) || 1)} />
        </Field>
        {dirty && (
          <Button onClick={() => save.mutate()} loading={save.isPending}>
            Save Gmail search
          </Button>
        )}
      </div>
    </div>
  );
}

export function GmailCard({ showSenders = true, returnTo }: { showSenders?: boolean; returnTo?: string }) {
  const connect = () => startGmailConnect(returnTo);
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const status = useGmailStatus();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: keys.gmail });
    queryClient.invalidateQueries({ queryKey: keys.integrations });
    queryClient.invalidateQueries({ queryKey: keys.stats });
  };
  const test = useMutation({
    mutationFn: () => api.post<{ ok: boolean; email: string; count: number }>("/api/integrations/gmail/test"),
    onSuccess: (result) => {
      toast.success(`Found ${result.count} alert email${result.count === 1 ? "" : "s"}`, { description: `Signed in as ${result.email}.` });
      refresh();
    },
    onError: (error: Error) => {
      toast.error("Gmail test failed", {
        description: error instanceof ApiError && error.status === 409 ? "Gmail needs to be connected first." : error.message,
      });
      refresh();
    },
  });
  const disconnect = useMutation({
    mutationFn: () => api.post<{ revoked: boolean; message: string }>("/api/integrations/gmail/disconnect"),
    onSuccess: (result) => {
      (result.revoked ? toast.success : toast.warning)("Gmail disconnected", {
        description: result.revoked ? "Google confirmed the access was revoked." : result.message,
      });
      refresh();
    },
    onError: (error: Error) => toast.error("Disconnect failed", { description: error.message }),
  });

  if (status.isPending) return <Card className="p-4"><SkeletonForm fields={3} /></Card>;
  if (status.isError) return <ErrorState error={status.error} onRetry={() => status.refetch()} />;
  const data = status.data;
  const { label, icon: Icon, tone } = STATE[data.state];

  return (
    <Card id="gmail" className="scroll-mt-20 space-y-4 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-0.5">
          <h3 className="flex items-center gap-2 text-section">
            <Mail className="size-4" /> Gmail
          </h3>
          <p className="max-w-prose text-body text-muted-foreground">
            Reads job-alert emails (LinkedIn, Indeed, StepStone, Jobat, VDAB, Actiris). Read-only: nothing is sent or changed.
          </p>
        </div>
        <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-caption font-medium", tone)} role="status">
          <Icon className="size-3.5" aria-hidden /> {data.state === "connected" && data.email ? `Connected as ${data.email}` : label}
        </span>
      </div>

      {!data.credentials_present ? (
        <div className="space-y-2 rounded-md border border-warning/30 bg-warning-soft p-3 text-body">
          <p className="flex items-center gap-2 font-medium text-warning">
            <FileKey2 className="size-4" /> credentials.json is missing
          </p>
          <p className="text-foreground/80">
            Create an OAuth client of type “Desktop app” in Google Cloud Console, enable the Gmail API, download the JSON
            and save it as <span className="font-mono">credentials.json</span> in the app folder. Then reload this page.
          </p>
          <a className="text-primary underline-offset-4 hover:underline" target="_blank" rel="noopener noreferrer"
            href="https://developers.google.com/gmail/api/quickstart/python#authorize_credentials_for_a_desktop_application">
            How to create credentials.json
          </a>
        </div>
      ) : (
        <p className="flex items-center gap-2 text-caption text-muted-foreground">
          <CheckCircle2 className="size-3.5 text-success" /> credentials.json found ({data.client_type === "web" ? "web client" : "desktop client"})
        </p>
      )}

      {data.client_type === "web" && (
        <p className="rounded-md bg-info-soft p-3 text-body text-info">
          Your OAuth client is a “Web application”. Add this redirect URI to it in Google Cloud Console:{" "}
          <span className="break-all font-mono">{data.redirect_uri}</span>
        </p>
      )}

      {(data.state === "reauth_required" || data.state === "error") && data.reason && (
        <p className={cn("rounded-md p-3 text-body", data.state === "error" ? "bg-danger-soft text-danger" : "bg-warning-soft text-warning")}>
          {data.reason}
        </p>
      )}

      {data.state === "connected" && (
        <dl className="grid gap-3 text-body sm:grid-cols-3">
          <div>
            <dt className="text-caption text-muted-foreground">Access</dt>
            <dd><Badge variant="success">{data.read_only ? "Read-only" : "Custom scopes"}</Badge></dd>
          </div>
          <div>
            <dt className="text-caption text-muted-foreground">Last fetch</dt>
            <dd>
              <RelativeTime value={data.last_fetch} />
              {data.last_message_count != null && <span className="text-muted-foreground tabular"> · {data.last_message_count} emails</span>}
            </dd>
          </div>
          <div>
            <dt className="text-caption text-muted-foreground">Token refreshed</dt>
            <dd><RelativeTime value={data.last_refresh} /></dd>
          </div>
        </dl>
      )}

      <div className="flex flex-wrap gap-2">
        {data.state === "not_connected" ? (
          <Button onClick={connect} disabled={!data.credentials_present}>
            <Mail /> Connect Gmail
          </Button>
        ) : data.state !== "connected" ? (
          <Button onClick={connect} disabled={!data.credentials_present}>
            <RefreshCw /> Reconnect
          </Button>
        ) : null}
        {data.state !== "not_connected" && (
          <Button variant="secondary" onClick={() => test.mutate()} loading={test.isPending}>
            <PlugZap /> Test connection
          </Button>
        )}
        {data.state === "connected" && (
          <Button variant="outline" onClick={connect}>
            <RefreshCw /> Reconnect
          </Button>
        )}
        {data.state !== "not_connected" && (
          <Button
            variant="ghost"
            className="text-danger hover:text-danger"
            loading={disconnect.isPending}
            onClick={async () => {
              const ok = await confirm({
                title: "Disconnect Gmail?",
                description: "The app's access token is revoked at Google and deleted from this computer. Runs skip Gmail until you connect again.",
                confirmLabel: "Disconnect and revoke",
                destructive: true,
              });
              if (ok) disconnect.mutate();
            }}
          >
            <LogOut /> Disconnect
          </Button>
        )}
      </div>
      {test.data && (
        <p className="text-body text-success" role="status">
          Test: found {test.data.count} alert email{test.data.count === 1 ? "" : "s"}.
        </p>
      )}
      <p className="text-caption text-muted-foreground">
        If your Google Cloud app is in <em>Testing</em> mode, Google expires access after 7 days. Reconnect, or publish the app for
        personal use.{" "}
        <a className={buttonVariants({ variant: "link", size: "sm" })} style={{ padding: 0, height: "auto" }} target="_blank" rel="noopener noreferrer"
          href="https://support.google.com/cloud/answer/10311615#publishing-status">
          About publishing status
        </a>
      </p>
      {showSenders && <SendersEditor />}
    </Card>
  );
}

/** Reads ?gmail=connected|denied|error&reason=… after Google redirects back, then cleans the URL. */
export function useGmailRedirectToast() {
  const queryClient = useQueryClient();
  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("gmail");
    if (!result) return;
    const reason = params.get("reason") ?? "";
    if (result === "connected") toast.success("Gmail connected", { description: "Run a test to see how many alert emails it finds." });
    else if (result === "denied") toast.warning("Gmail was not connected", { description: reason });
    else toast.error("Gmail could not be connected", { description: reason });
    params.delete("gmail");
    params.delete("reason");
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
    queryClient.invalidateQueries({ queryKey: keys.gmail });
    queryClient.invalidateQueries({ queryKey: keys.integrations });
  }, [queryClient]);
}
