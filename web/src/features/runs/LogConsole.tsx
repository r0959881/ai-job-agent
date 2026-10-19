import { Copy, Pause, Play } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/controls";
import type { LogLevel, LogLine } from "@/features/runs/runSteps";
import { cn, formatAbsolute } from "@/lib/utils";

const LEVELS: { level: LogLevel; label: string }[] = [
  { level: "info", label: "Info" },
  { level: "warning", label: "Warnings" },
  { level: "error", label: "Errors" },
];

export function LogConsole({ lines, live }: { lines: LogLine[]; live: boolean }) {
  const [paused, setPaused] = React.useState(false);
  const [levels, setLevels] = React.useState<Set<LogLevel>>(new Set(["info", "warning", "error"]));
  const scroller = React.useRef<HTMLDivElement>(null);
  const visible = lines.filter((line) => levels.has(line.level));
  const counts = { warning: lines.filter((l) => l.level === "warning").length, error: lines.filter((l) => l.level === "error").length };

  React.useEffect(() => {
    if (!paused && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [visible.length, paused]);

  const copy = async () => {
    const text = visible.map((line) => `${line.ts} ${line.level.toUpperCase()} ${line.text}`).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`Copied ${visible.length} log line(s)`);
    } catch {
      toast.error("Your browser blocked clipboard access.");
    }
  };

  return (
    <div className="flex flex-col overflow-hidden rounded-lg border">
      <div className="flex flex-wrap items-center gap-3 border-b bg-muted/40 px-3 py-2">
        <span className="text-body font-medium">Log</span>
        <div className="flex flex-wrap items-center gap-3" role="group" aria-label="Show log levels">
          {LEVELS.map(({ level, label }) => (
            <label key={level} className="flex items-center gap-1.5 text-body">
              <Checkbox
                checked={levels.has(level)}
                onCheckedChange={(checked) =>
                  setLevels((current) => {
                    const next = new Set(current);
                    if (checked) next.add(level);
                    else next.delete(level);
                    return next;
                  })
                }
              />
              {label}
              {level !== "info" && counts[level] > 0 && <span className="tabular text-muted-foreground">({counts[level]})</span>}
            </label>
          ))}
        </div>
        <div className="ml-auto flex gap-1">
          {live && (
            <Button size="sm" variant="ghost" onClick={() => setPaused((p) => !p)} aria-pressed={paused}>
              {paused ? <Play /> : <Pause />} {paused ? "Resume scroll" : "Pause scroll"}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={copy} disabled={!visible.length}>
            <Copy /> Copy
          </Button>
        </div>
      </div>
      <div
        ref={scroller}
        className="h-[420px] overflow-y-auto bg-background p-3 font-mono text-[12px] leading-5"
        role="log"
        aria-live={live && !paused ? "polite" : "off"}
        aria-relevant="additions"
        tabIndex={0}
        onWheel={(event) => {
          if (live && event.deltaY < 0 && !paused) setPaused(true);
        }}
      >
        {visible.length === 0 && <p className="text-muted-foreground">{live ? "Waiting for output…" : "No log lines match the filters."}</p>}
        {visible.map((line) => (
          <div
            key={line.seq}
            className={cn(
              "whitespace-pre-wrap break-words",
              line.level === "warning" && "text-warning",
              line.level === "error" && "text-danger",
            )}
          >
            <time className="mr-2 select-none text-muted-foreground" title={formatAbsolute(line.ts)}>
              {new Date(line.ts).toLocaleTimeString("en-GB", { timeZone: "Europe/Brussels" })}
            </time>
            {line.text}
          </div>
        ))}
      </div>
    </div>
  );
}
