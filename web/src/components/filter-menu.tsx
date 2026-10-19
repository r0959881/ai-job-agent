import { ChevronDown } from "lucide-react";
import { Checkbox } from "@/components/ui/controls";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/overlays";
import { cn } from "@/lib/utils";

/** A toolbar button that opens a checklist of filter values. */
export function FilterMenu({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const active = value.length > 0;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-md border border-dashed border-input px-3 text-caption font-medium hover:bg-muted",
            active && "border-solid border-primary/50 bg-accent text-accent-foreground",
          )}
        >
          {label}
          {active && (
            <span className="rounded bg-primary px-1 tabular text-primary-foreground">{value.length}</span>
          )}
          <ChevronDown className="size-3.5 opacity-60" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-60 p-1">
        <ul className="max-h-72 overflow-y-auto" aria-label={label}>
          {options.length === 0 && (
            <li className="px-2 py-2 text-body text-muted-foreground">No values yet.</li>
          )}
          {options.map((option) => {
            const checked = value.includes(option.value);
            return (
              <li key={option.value}>
                <label className="flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-body hover:bg-muted">
                  <Checkbox
                    checked={checked}
                    onCheckedChange={(on) =>
                      onChange(on ? [...value, option.value] : value.filter((v) => v !== option.value))
                    }
                  />
                  <span className="truncate">{option.label}</span>
                </label>
              </li>
            );
          })}
        </ul>
        {active && (
          <button
            type="button"
            className="mt-1 w-full rounded-sm border-t px-2 py-1.5 text-left text-caption text-muted-foreground hover:bg-muted"
            onClick={() => onChange([])}
          >
            Clear {label.toLowerCase()}
          </button>
        )}
      </PopoverContent>
    </Popover>
  );
}
