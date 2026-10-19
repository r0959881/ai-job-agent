import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { GmailAttentionBanner } from "@/features/integrations/GmailAttentionBanner";
import { Field } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Checkbox, Switch } from "@/components/ui/controls";
import { Input } from "@/components/ui/primitives";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/overlays";
import { ApiError, api } from "@/lib/api";
import { keys, useIntegrations } from "@/lib/queries";
import type { RunOptions, SettingsResponse } from "@/lib/types";

const SOURCES = [
  { key: "adzuna", label: "Adzuna", hint: "Belgian job API" },
  { key: "arbeitnow", label: "Arbeitnow", hint: "Public job board" },
  { key: "gmail", label: "Gmail alerts", hint: "LinkedIn, Indeed, StepStone, VDAB… alert emails" },
] as const;

export function StartRunDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: keys.settings,
    queryFn: () => api.get<SettingsResponse>("/api/settings/search"),
    enabled: open,
  });
  const integrations = useIntegrations();
  const [options, setOptions] = React.useState<RunOptions>({
    sources: ["adzuna", "arbeitnow", "gmail"],
    time_window_hours: 48,
    max_tailor: null,
    dry_run: false,
  });

  React.useEffect(() => {
    const s = settings.data?.settings;
    if (open && s) {
      setOptions((current) => ({
        ...current,
        sources: SOURCES.map((source) => source.key).filter((key) => s.sources[key]),
        time_window_hours: s.time_window_hours,
      }));
    }
  }, [open, settings.data]);

  const start = useMutation({
    mutationFn: () => api.post<{ id: number }>("/api/runs", options),
    onSuccess: ({ id }) => {
      toast.success(`Run #${id} started`, { description: "Follow its progress on the run page." });
      queryClient.invalidateQueries({ queryKey: keys.runs });
      onOpenChange(false);
      navigate(`/runs/${id}`);
      if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission().catch(() => undefined);
      }
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        const runId = (error.detail as { run_id?: number })?.run_id;
        toast.error("A run is already in progress", {
          description: "Only one run can happen at a time.",
          action: runId ? { label: "Open it", onClick: () => navigate(`/runs/${runId}`) } : undefined,
        });
      } else {
        toast.error("The run did not start", { description: (error as Error).message });
      }
    },
  });

  const toggleSource = (key: string, on: boolean) =>
    setOptions((current) => ({
      ...current,
      sources: on ? [...current.sources, key] : current.sources.filter((s) => s !== key),
    }));

  const groqMissing = integrations.data?.groq.status === "missing";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Start a run</DialogTitle>
          <DialogDescription>
            Searches the selected sources, filters for eligible jobs and tailors a CV for each new one.
          </DialogDescription>
        </DialogHeader>
        <GmailAttentionBanner compact />
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            start.mutate();
          }}
        >
          <fieldset className="space-y-2">
            <legend className="mb-1 text-body font-medium">Sources</legend>
            {SOURCES.map((source) => (
              <label
                key={source.key}
                className="flex items-start gap-3 rounded-md border p-3 hover:bg-muted/50"
              >
                <Checkbox
                  checked={options.sources.includes(source.key)}
                  onCheckedChange={(checked) => toggleSource(source.key, checked === true)}
                  className="mt-0.5"
                />
                <span>
                  <span className="block font-medium">{source.label}</span>
                  <span className="block text-caption text-muted-foreground">{source.hint}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Time window (hours)"
              htmlFor="run-window"
              description="Jobs posted or found within this window."
            >
              <Input
                id="run-window"
                type="number"
                min={1}
                max={720}
                className="tabular"
                value={options.time_window_hours}
                onChange={(e) => setOptions({ ...options, time_window_hours: Number(e.target.value) || 48 })}
              />
            </Field>
            <Field label="Max CVs to tailor" htmlFor="run-max" description="Leave empty for no limit.">
              <Input
                id="run-max"
                type="number"
                min={0}
                className="tabular"
                placeholder="No limit"
                value={options.max_tailor ?? ""}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    max_tailor: e.target.value === "" ? null : Math.max(0, Number(e.target.value)),
                  })
                }
              />
            </Field>
          </div>
          <label className="flex items-center justify-between gap-4 rounded-md border p-3">
            <span>
              <span className="block font-medium">Dry run</span>
              <span className="block text-caption text-muted-foreground">
                Discover and filter only. No CVs are generated.
              </span>
            </span>
            <Switch
              checked={options.dry_run}
              onCheckedChange={(dry_run) => setOptions({ ...options, dry_run })}
            />
          </label>
          {groqMissing && !options.dry_run && (
            <p className="rounded-md bg-warning-soft p-3 text-body text-warning">
              GROQ_API_KEY is not set, so tailoring will be skipped. Add it in Settings → Integrations.
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={start.isPending} disabled={!options.sources.length}>
              <Play /> Start run
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
