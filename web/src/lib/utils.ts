import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Our type scale (text-caption/body/section/title) is a font size, not a colour; without this,
// twMerge would drop text-primary-foreground from small buttons and leave dark text on indigo.
const twMerge = extendTailwindMerge({
  extend: { classGroups: { "font-size": [{ text: ["caption", "body", "section", "title"] }] } },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const TIME_ZONE = "Europe/Brussels";

const absoluteFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: TIME_ZONE,
  dateStyle: "medium",
  timeStyle: "short",
});
const dateFormat = new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, dateStyle: "medium" });
const shortDateTimeFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: TIME_ZONE,
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const relativeFormat = new Intl.RelativeTimeFormat("en", { numeric: "auto", style: "narrow" });

export function parseDate(value?: string | null): Date | null {
  if (!value) return null;
  // SQLite's datetime('now') has no zone and is UTC.
  const normalised = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
    ? `${value.replace(" ", "T")}Z`
    : value;
  const date = new Date(normalised);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatAbsolute(value?: string | null) {
  const date = parseDate(value);
  return date ? `${absoluteFormat.format(date)} (Brussels)` : "";
}

export function formatDate(value?: string | null) {
  const date = parseDate(value);
  return date ? dateFormat.format(date) : "";
}

/** "21 Oct, 09:14" (Brussels time), for tables. */
export function formatShortDateTime(value?: string | null) {
  const date = parseDate(value);
  return date ? shortDateTimeFormat.format(date) : "";
}

export function formatRelative(value?: string | null, now = Date.now()) {
  const date = parseDate(value);
  if (!date) return "";
  const seconds = Math.round((date.getTime() - now) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return "just now";
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["minute", 60],
    ["hour", 3600],
    ["day", 86400],
    ["week", 604800],
    ["month", 2629800],
    ["year", 31557600],
  ];
  let chosen: [Intl.RelativeTimeFormatUnit, number] = units[0];
  for (const unit of units) if (abs >= unit[1]) chosen = unit;
  return relativeFormat.format(Math.round(seconds / chosen[1]), chosen[0]);
}

export function formatDuration(seconds?: number | null) {
  if (seconds == null) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${rest}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function plural(count: number, word: string, pluralWord = `${word}s`) {
  return `${count} ${count === 1 ? word : pluralWord}`;
}

export function formatSalary(min?: number | null, max?: number | null, currency?: string | null) {
  if (min == null && max == null) return "";
  const fmt = (n: number) => new Intl.NumberFormat("en-BE", { maximumFractionDigits: 0 }).format(n);
  const symbol = currency || "€";
  if (min != null && max != null && min !== max) return `${symbol}${fmt(min)}–${fmt(max)}`;
  return `${symbol}${fmt((min ?? max) as number)}`;
}

export function fileName(path?: string | null) {
  if (!path) return "";
  return path.split(/[\\/]/).pop() ?? path;
}
