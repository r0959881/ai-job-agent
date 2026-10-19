import { Check, Copy, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge, type BadgeVariant } from "@/components/ui/primitives";
import { Tooltip } from "@/components/ui/overlays";
import { cn, formatAbsolute, formatRelative } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="mb-6 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-title">{title}</h1>
          {description && <p className="max-w-prose text-body text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

export function RelativeTime({ value, className }: { value?: string | null; className?: string }) {
  const [, force] = React.useReducer((n: number) => n + 1, 0);
  React.useEffect(() => {
    const timer = window.setInterval(force, 60_000);
    return () => window.clearInterval(timer);
  }, []);
  if (!value) return <span className={cn("text-muted-foreground", className)}>—</span>;
  return (
    <Tooltip content={formatAbsolute(value)}>
      <time dateTime={value} className={cn("tabular", className)} tabIndex={0}>
        {formatRelative(value)}
      </time>
    </Tooltip>
  );
}

export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = React.useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success(`${label} copied`);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Your browser blocked clipboard access. Select the text and copy it manually.");
    }
  };
  return (
    <Button variant="outline" size="icon-sm" onClick={copy} aria-label={`Copy ${label}`} disabled={!value}>
      {copied ? <Check className="text-success" /> : <Copy />}
    </Button>
  );
}

export function TagInput({
  value,
  onChange,
  placeholder = "Type and press Enter",
  id,
  "aria-label": ariaLabel,
  className,
  suggestions,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  id?: string;
  "aria-label"?: string;
  className?: string;
  suggestions?: string[];
}) {
  const [draft, setDraft] = React.useState("");
  const listId = React.useId();
  const add = (raw: string) => {
    const items = raw
      .split(/[,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (!items.length) return;
    const lower = new Set(value.map((v) => v.toLowerCase()));
    const fresh = items.filter((item) => !lower.has(item.toLowerCase()));
    if (fresh.length) onChange([...value, ...fresh]);
    setDraft("");
  };
  return (
    <div
      className={cn(
        "flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2 py-1.5 shadow-sm focus-within:ring-2 focus-within:ring-ring",
        className,
      )}
    >
      {value.map((tag, index) => (
        <Badge key={`${tag}-${index}`} variant="accent" className="gap-0.5 pr-1">
          {tag}
          <button
            type="button"
            className="rounded-full p-0.5 hover:bg-primary/15"
            aria-label={`Remove ${tag}`}
            onClick={() => onChange(value.filter((_, i) => i !== index))}
          >
            <X className="size-3" />
          </button>
        </Badge>
      ))}
      <input
        id={id}
        aria-label={ariaLabel}
        list={suggestions?.length ? listId : undefined}
        className="min-w-[8rem] flex-1 bg-transparent text-body outline-none placeholder:text-muted-foreground"
        placeholder={value.length ? "" : placeholder}
        value={draft}
        onChange={(event) => {
          const next = event.target.value;
          if (next.includes(",")) add(next);
          else setDraft(next);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            add(draft);
          } else if (event.key === "Backspace" && !draft && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={() => add(draft)}
        onPaste={(event) => {
          const text = event.clipboardData.getData("text");
          if (/[,\n]/.test(text)) {
            event.preventDefault();
            add(text);
          }
        }}
      />
      {suggestions?.length ? (
        <datalist id={listId}>
          {suggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      ) : null}
    </div>
  );
}

const APPLICATION_STATUS: Record<string, { label: string; variant: BadgeVariant }> = {
  not_applied: { label: "Not applied", variant: "secondary" },
  applied: { label: "Applied", variant: "info" },
  interviewing: { label: "Interviewing", variant: "accent" },
  offer: { label: "Offer", variant: "success" },
  rejected: { label: "Rejected", variant: "danger" },
  skipped: { label: "Skipped", variant: "outline" },
};

export const APPLICATION_STATUS_OPTIONS = Object.entries(APPLICATION_STATUS).map(([value, { label }]) => ({
  value,
  label,
}));

export function ApplicationStatusBadge({ status }: { status: string }) {
  const info = APPLICATION_STATUS[status] ?? APPLICATION_STATUS.not_applied;
  return <Badge variant={info.variant}>{info.label}</Badge>;
}

const RUN_STATUS: Record<string, { label: string; variant: BadgeVariant }> = {
  running: { label: "Running", variant: "info" },
  succeeded: { label: "Succeeded", variant: "success" },
  failed: { label: "Failed", variant: "danger" },
  cancelled: { label: "Cancelled", variant: "warning" },
};

export function RunStatusBadge({ status }: { status: string }) {
  const info = RUN_STATUS[status] ?? { label: status, variant: "secondary" as BadgeVariant };
  return <Badge variant={info.variant}>{info.label}</Badge>;
}

export function JobStatusBadge({ status }: { status: string }) {
  const variant: BadgeVariant = status === "processed" ? "success" : status === "rejected" ? "outline" : "secondary";
  const label = status === "processed" ? "CV ready" : status === "rejected" ? "Filtered out" : "New";
  return <Badge variant={variant}>{label}</Badge>;
}

export function SourceBadge({ source }: { source: string }) {
  const first = (source || "Unknown").split("|")[0].trim();
  const extra = (source || "").split("|").length - 1;
  return (
    <Tooltip content={extra ? source : undefined}>
      <Badge variant="outline" className="max-w-[12rem] truncate">
        {first}
        {extra ? ` +${extra}` : ""}
      </Badge>
    </Tooltip>
  );
}

export function Field({
  label,
  htmlFor,
  description,
  error,
  children,
  className,
}: {
  label: React.ReactNode;
  htmlFor?: string;
  description?: React.ReactNode;
  error?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="text-body font-medium">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-caption text-danger" role="alert">
          {error}
        </p>
      ) : description ? (
        <p className="text-caption text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}
