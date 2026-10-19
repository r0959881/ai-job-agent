import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { Briefcase, Play, Plus } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { NAV_ITEMS } from "@/components/layout/AppShell";
import { useStartRun } from "@/components/layout/RunControl";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/overlays";
import { api, query } from "@/lib/api";
import type { JobsPage } from "@/lib/types";

const itemClass =
  "flex cursor-default select-none items-center gap-2 rounded-md px-2 py-2 text-body aria-selected:bg-muted [&_svg]:size-4 [&_svg]:text-muted-foreground";
const groupClass =
  "[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-caption [&_[cmdk-group-heading]]:text-muted-foreground";

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const startRun = useStartRun();
  const [search, setSearch] = React.useState("");
  const [debounced, setDebounced] = React.useState("");

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 200);
    return () => window.clearTimeout(timer);
  }, [search]);

  const jobs = useQuery({
    queryKey: ["palette-jobs", debounced],
    queryFn: () => api.get<JobsPage>(`/api/jobs${query({ q: debounced, page_size: 8 })}`),
    enabled: open && debounced.length >= 2,
  });

  const go = (action: () => void) => {
    onOpenChange(false);
    setSearch("");
    action();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl overflow-hidden p-0">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <Command label="Command palette" shouldFilter={false} className="flex flex-col">
          <Command.Input
            value={search}
            onValueChange={setSearch}
            placeholder="Type a command or search jobs…"
            className="h-12 border-b bg-transparent px-4 text-body outline-none placeholder:text-muted-foreground"
          />
          <Command.List className="max-h-[360px] overflow-y-auto p-2">
            <Command.Empty className="px-2 py-6 text-center text-body text-muted-foreground">
              No matches for “{search}”.
            </Command.Empty>
            <Command.Group heading="Actions" className={groupClass}>
              {matches(search, "Run agent start search") && (
                <Command.Item className={itemClass} onSelect={() => go(startRun)}>
                  <Play /> Run agent
                </Command.Item>
              )}
              {matches(search, "Add experience profile") && (
                <Command.Item
                  className={itemClass}
                  onSelect={() => go(() => navigate("/profile?add=experience#experience"))}
                >
                  <Plus /> Add experience
                </Command.Item>
              )}
            </Command.Group>
            <Command.Group heading="Go to" className={groupClass}>
              {NAV_ITEMS.filter((item) => matches(search, item.label)).map(({ to, label, icon: Icon }) => (
                <Command.Item key={to} className={itemClass} onSelect={() => go(() => navigate(to))}>
                  <Icon /> {label}
                </Command.Item>
              ))}
            </Command.Group>
            {jobs.data?.items.length ? (
              <Command.Group heading="Jobs" className={groupClass}>
                {jobs.data.items.map((job) => (
                  <Command.Item
                    key={job.id}
                    className={itemClass}
                    onSelect={() => go(() => navigate(`/jobs/${job.id}`))}
                  >
                    <Briefcase />
                    <span className="truncate">{job.title}</span>
                    <span className="ml-auto shrink-0 truncate text-caption text-muted-foreground">
                      {job.company}
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            ) : null}
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}

function matches(search: string, text: string) {
  const needle = search.trim().toLowerCase();
  return !needle || text.toLowerCase().includes(needle);
}
