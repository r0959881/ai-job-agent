import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Field, TagInput } from "@/components/common";
import { SkeletonForm } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Badge, Card, Input } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { SettingsResponse } from "@/lib/types";

/** Onboarding's short version of Settings → Search: pick which role families to search for. */
export function TargetRolesQuick() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: keys.settings, queryFn: () => api.get<SettingsResponse>("/api/settings/search") });
  const [name, setName] = React.useState("");
  const [keywords, setKeywords] = React.useState<string[]>([]);
  const save = useMutation({
    mutationFn: (roles: Record<string, string[]>) => {
      const current = settings.data!.settings;
      const queries = Object.fromEntries(
        Object.keys(roles).map((role) => [role, current.search_queries[role] ?? roles[role].slice(0, 2)]),
      );
      return api.put<SettingsResponse>("/api/settings/search", { settings: { ...current, target_roles: roles, search_queries: queries } });
    },
    onSuccess: (result) => {
      queryClient.setQueryData(keys.settings, result);
      toast.success("Target roles saved");
    },
    onError: (error: Error) => toast.error("Target roles were not saved", { description: error.message }),
  });
  if (!settings.data) return <SkeletonForm fields={2} />;
  const roles = settings.data.settings.target_roles;

  return (
    <Card className="space-y-4 p-4">
      <div>
        <h3 className="text-section">Target roles</h3>
        <p className="text-body text-muted-foreground">
          The agent searches for these role families and picks the matching role profile for each CV. Fine-tune keywords
          later in Settings → Search.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {Object.entries(roles).map(([role, words]) => (
          <Badge key={role} variant="accent" className="gap-1 py-1 pl-3 pr-1 text-body" title={words.join(", ")}>
            {role}
            <button
              type="button"
              aria-label={`Remove ${role}`}
              className="rounded-full p-0.5 hover:bg-primary/15"
              disabled={Object.keys(roles).length === 1 || save.isPending}
              onClick={() => {
                const next = { ...roles };
                delete next[role];
                save.mutate(next);
              }}
            >
              <X className="size-3.5" />
            </button>
          </Badge>
        ))}
      </div>
      <form
        className="grid gap-3 md:grid-cols-[14rem_1fr_auto] md:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim() || !keywords.length) {
            toast.error("Give the role a name and at least one keyword.");
            return;
          }
          save.mutate({ ...roles, [name.trim()]: keywords });
          setName("");
          setKeywords([]);
        }}
      >
        <Field label="New role" htmlFor="role-name">
          <Input id="role-name" placeholder="e.g. BI Developer" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Title keywords" htmlFor="role-keywords">
          <TagInput id="role-keywords" value={keywords} onChange={setKeywords} placeholder="bi developer, power bi developer" />
        </Field>
        <Button type="submit" variant="outline" loading={save.isPending}>
          <Plus /> Add role
        </Button>
      </form>
    </Card>
  );
}
