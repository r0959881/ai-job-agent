/*
 * Thin fetch wrapper: JSON in/out, the session's CSRF token, readable errors.
 *
 * Paths for jobs, documents, runs and stats are answered on this device
 * (lib/local/routes.ts); everything else goes to the server.
 */

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export interface SessionUser {
  id: number;
  email: string;
  name: string;
  picture: string;
  providers: string[];
}

export interface SessionInfo {
  user: SessionUser | null;
  csrf: string;
  providers: { id: string; label: string }[];
  /** The local account on your own PC: files go to the project's output/ folder. */
  project_files: boolean;
}

export const SIGNED_OUT_EVENT = "session-signed-out";

let sessionPromise: Promise<SessionInfo> | null = null;

export function getSession(refresh = false): Promise<SessionInfo> {
  if (!sessionPromise || refresh) {
    sessionPromise = fetch("/api/session", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then((r) => {
        if (!r.ok) throw new ApiError(r.status, "The server is not responding. Try again in a minute.", null);
        return r.json() as Promise<SessionInfo>;
      })
      .catch((error) => {
        sessionPromise = null;
        throw error instanceof ApiError
          ? error
          : new ApiError(0, "The server is not responding. Check your connection and try again.", null);
      });
  }
  return sessionPromise;
}

export function messageFromDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const loc = Array.isArray((item as { loc?: unknown[] }).loc)
            ? ((item as { loc: unknown[] }).loc.filter((p) => p !== "body").join(" › ") as string)
            : "";
          return loc ? `${loc}: ${(item as { msg: string }).msg}` : (item as { msg: string }).msg;
        }
        return String(item);
      })
      .slice(0, 3);
    return parts.join("; ") || fallback;
  }
  if (detail && typeof detail === "object" && "message" in detail)
    return String((detail as { message: string }).message);
  return fallback;
}

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** A request to the server itself (never answered locally). */
export async function serverRequest<T>(
  method: string,
  url: string,
  body?: unknown,
  retry = true,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body instanceof Blob) {
    headers["Content-Type"] = "application/octet-stream";
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (MUTATING.has(method)) headers["X-CSRF-Token"] = (await getSession()).csrf;

  let response: Response;
  try {
    response = await fetch(url, { method, headers, body: payload, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "The server is not responding. Check your connection and try again.", null);
  }
  const text = await response.text();
  const data = text ? safeJson(text) : null;
  const detail =
    data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : data;
  if (
    response.status === 403 &&
    retry &&
    MUTATING.has(method) &&
    (data as { code?: string })?.code === "csrf"
  ) {
    await getSession(true);
    return serverRequest<T>(method, url, body, false);
  }
  if (response.status === 401) {
    sessionPromise = null;
    window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      messageFromDetail(detail, `Request failed (${response.status}).`),
      detail,
    );
  }
  return data as T;
}

export async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const local = await import("@/lib/local/routes");
  if (local.isLocal(url)) return (await local.handleLocal(method, url, body)) as T;
  return serverRequest<T>(method, url, body);
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T>(url: string, body?: unknown) => request<T>("POST", url, body ?? {}),
  put: <T>(url: string, body: unknown) => request<T>("PUT", url, body),
  patch: <T>(url: string, body: unknown) => request<T>("PATCH", url, body),
  delete: <T>(url: string) => request<T>("DELETE", url),
  upload: <T>(url: string, file: File, fields: Record<string, string> = {}) => {
    const form = new FormData();
    form.append("file", file);
    for (const [key, value] of Object.entries(fields)) form.append(key, value);
    return request<T>("POST", url, form);
  },
};

export function query(params: Record<string, string | number | boolean | undefined | null | string[]>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v));
    else search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
