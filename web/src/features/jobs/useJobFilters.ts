import * as React from "react";
import { useSearchParams } from "react-router-dom";

export interface JobFilters {
  q: string;
  status: string[];
  application_status: string[];
  role_family: string[];
  source: string[];
  date_from: string;
  date_to: string;
  has_cv: "" | "true" | "false";
  quick: "" | "ready" | "applied_week" | "follow_up";
  /** When the job was added to the app: last hour, day, week, or by the latest run. */
  added: "" | "1h" | "24h" | "7d" | "run";
  sort: string;
  order: "asc" | "desc";
  page: number;
  page_size: number;
}

const LIST_KEYS = ["status", "application_status", "role_family", "source"] as const;

/** Job filters live in the URL so they survive reloads and can be bookmarked. */
export function useJobFilters() {
  const [params, setParams] = useSearchParams();
  const filters: JobFilters = {
    q: params.get("q") ?? "",
    status: params.getAll("status"),
    application_status: params.getAll("application_status"),
    role_family: params.getAll("role_family"),
    source: params.getAll("source"),
    date_from: params.get("date_from") ?? "",
    date_to: params.get("date_to") ?? "",
    has_cv: (params.get("has_cv") as JobFilters["has_cv"]) ?? "",
    quick: (params.get("quick") as JobFilters["quick"]) ?? "",
    added: (params.get("added") as JobFilters["added"]) ?? "",
    sort: params.get("sort") ?? "posted",
    order: params.get("order") === "asc" ? "asc" : "desc",
    page: Math.max(1, Number(params.get("page") ?? 1) || 1),
    page_size: Number(params.get("page_size") ?? 50) || 50,
  };

  const update = React.useCallback(
    (changes: Partial<JobFilters>, resetPage = true) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, value] of Object.entries(changes)) {
            next.delete(key);
            if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
            else if (value !== "" && value != null) next.set(key, String(value));
          }
          if (resetPage && !("page" in changes)) next.delete("page");
          if (next.get("sort") === "posted") next.delete("sort");
          if (next.get("order") === "desc") next.delete("order");
          if (next.get("page") === "1") next.delete("page");
          if (next.get("page_size") === "50") next.delete("page_size");
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const clear = React.useCallback(() => setParams(new URLSearchParams(), { replace: true }), [setParams]);
  const activeCount =
    LIST_KEYS.reduce((n, key) => n + (filters[key].length ? 1 : 0), 0) +
    (filters.q ? 1 : 0) +
    (filters.date_from || filters.date_to ? 1 : 0) +
    (filters.has_cv ? 1 : 0) +
    (filters.quick ? 1 : 0) +
    (filters.added ? 1 : 0);

  const apiQuery = React.useMemo(() => {
    const search = new URLSearchParams();
    if (filters.q) search.set("q", filters.q);
    for (const key of LIST_KEYS) filters[key].forEach((v) => search.append(key, v));
    if (filters.date_from) search.set("date_from", filters.date_from);
    if (filters.date_to) search.set("date_to", filters.date_to);
    if (filters.has_cv) search.set("has_cv", filters.has_cv);
    if (filters.quick) search.set("quick", filters.quick);
    if (filters.added) search.set("added", filters.added);
    search.set("sort", filters.sort);
    search.set("order", filters.order);
    search.set("page", String(filters.page));
    search.set("page_size", String(filters.page_size));
    return search.toString();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  return { filters, update, clear, activeCount, apiQuery };
}
