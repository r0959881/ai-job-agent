import { AlertTriangle, Check, ChevronDown, X } from "lucide-react";
import * as React from "react";
import { Badge } from "@/components/ui/primitives";
import { Popover, PopoverContent, PopoverTrigger, Tooltip } from "@/components/ui/overlays";
import { cn } from "@/lib/utils";

/** Pick several values from a list. Selected values missing from `options` get a warning chip. */
export function MultiSelect({
  value,
  onChange,
  options,
  placeholder = "Choose…",
  id,
  "aria-label": ariaLabel,
  formatOption = (option: string) => option,
  missingHint = "This no longer exists",
}: {
  value: string[];
  onChange: (next: string[]) => void;
  options: string[];
  placeholder?: string;
  id?: string;
  "aria-label"?: string;
  formatOption?: (option: string) => string;
  missingHint?: string;
}) {
  const [filter, setFilter] = React.useState("");
  const known = new Set(options);
  const visible = options.filter((option) =>
    formatOption(option).toLowerCase().includes(filter.toLowerCase()),
  );
  const toggle = (option: string) =>
    onChange(value.includes(option) ? value.filter((v) => v !== option) : [...value, option]);

  return (
    <div className="space-y-2">
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((item) => {
            const missing = !known.has(item);
            return (
              <Badge key={item} variant={missing ? "warning" : "accent"} className="gap-1 pr-1">
                {missing && (
                  <Tooltip content={missingHint}>
                    <AlertTriangle className="size-3" aria-label={missingHint} />
                  </Tooltip>
                )}
                {formatOption(item)}
                <button
                  type="button"
                  className="-my-1 rounded-full p-1.5 hover:bg-foreground/10"
                  onClick={() => toggle(item)}
                  aria-label={`Remove ${formatOption(item)}`}
                >
                  <X className="size-3" />
                </button>
              </Badge>
            );
          })}
        </div>
      )}
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            id={id}
            aria-label={ariaLabel}
            className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 text-body text-muted-foreground shadow-sm hover:bg-muted/50"
          >
            {placeholder}
            <ChevronDown className="size-4 opacity-60" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0">
          {options.length > 6 && (
            <input
              autoFocus
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Filter…"
              aria-label="Filter options"
              className="h-9 w-full border-b bg-transparent px-3 text-body outline-none"
            />
          )}
          <ul role="listbox" aria-multiselectable className="max-h-64 overflow-y-auto p-1">
            {visible.length === 0 && (
              <li className="px-2 py-2 text-body text-muted-foreground">Nothing to choose yet.</li>
            )}
            {visible.map((option) => {
              const selected = value.includes(option);
              return (
                <li key={option} role="option" aria-selected={selected}>
                  <button
                    type="button"
                    onClick={() => toggle(option)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-body hover:bg-muted",
                      selected && "font-medium",
                    )}
                  >
                    <span className="flex size-4 items-center justify-center">
                      {selected && <Check className="size-4 text-primary" />}
                    </span>
                    {formatOption(option)}
                  </button>
                </li>
              );
            })}
          </ul>
        </PopoverContent>
      </Popover>
    </div>
  );
}
