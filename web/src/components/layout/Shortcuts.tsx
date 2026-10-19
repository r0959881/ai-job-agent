import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Kbd } from "@/components/ui/primitives";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/overlays";

const GO: Record<string, { to: string; label: string }> = {
  d: { to: "/", label: "Dashboard" },
  p: { to: "/profile", label: "Profile" },
  j: { to: "/jobs", label: "Jobs" },
  o: { to: "/documents", label: "Documents" },
  r: { to: "/runs", label: "Runs" },
  s: { to: "/settings", label: "Settings" },
};

const LIST: [string[], string][] = [
  [["Ctrl", "K"], "Command palette (navigate, run the agent, search jobs)"],
  [["Ctrl", "S"], "Save the profile"],
  [["?"], "Show this list"],
  ...Object.entries(GO).map(([key, { label }]) => [["g", key], `Go to ${label}`] as [string[], string]),
];

function typing(target: EventTarget | null) {
  const element = target as HTMLElement | null;
  return Boolean(element?.closest("input, textarea, select, [contenteditable=true], .cm-editor"));
}

/** Global single-key shortcuts. Ignored while typing in a field. */
export function Shortcuts() {
  const navigate = useNavigate();
  const [open, setOpen] = React.useState(false);
  const pendingG = React.useRef(0);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) return;
      if (event.key === "?") {
        event.preventDefault();
        setOpen(true);
        return;
      }
      if (event.key === "g") {
        pendingG.current = Date.now();
        return;
      }
      const target = GO[event.key];
      if (target && Date.now() - pendingG.current < 1200) {
        event.preventDefault();
        pendingG.current = 0;
        navigate(target.to);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>
            Single-key shortcuts do nothing while you are typing in a field.
          </DialogDescription>
        </DialogHeader>
        <dl className="space-y-2">
          {LIST.map(([keys, label]) => (
            <div key={label} className="flex items-center justify-between gap-4 text-body">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="flex shrink-0 gap-1">
                {keys.map((key, index) => (
                  <Kbd key={index}>{key}</Kbd>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
