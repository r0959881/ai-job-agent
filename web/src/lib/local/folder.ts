/*
 * The folder the user picked for CVs, letters, reports and the jobs file (Chrome and Edge).
 *
 * The folder handle is kept in IndexedDB. Browsers ask again for permission after
 * a restart; until the user clicks "Reconnect", files are kept in browser storage.
 */
import * as idb from "@/lib/local/idb";

export const FOLDERS = {
  cv: "CVs",
  cover_letter: "Cover letters",
  report: "Reports",
  other: "Other",
} as const;
export const DATA_FILE = "ai-job-agent-data.json";
const HANDLE_KEY = "folder";

type Permission = "granted" | "denied" | "prompt";

interface PermissionHandle extends FileSystemDirectoryHandle {
  queryPermission(options: { mode: "readwrite" }): Promise<Permission>;
  requestPermission(options: { mode: "readwrite" }): Promise<Permission>;
  values(): AsyncIterable<FileSystemDirectoryHandle | FileSystemFileHandle>;
}

declare global {
  interface Window {
    showDirectoryPicker?: (options?: {
      id?: string;
      mode?: "readwrite";
      startIn?: string;
    }) => Promise<FileSystemDirectoryHandle>;
  }
}

export type FolderState =
  | { status: "project"; name: string }
  | { status: "unsupported" }
  | { status: "none" }
  | { status: "needs-permission"; name: string }
  | { status: "ready"; name: string };

export function folderSupported() {
  return typeof window !== "undefined" && typeof window.showDirectoryPicker === "function";
}

async function storedHandle(): Promise<PermissionHandle | undefined> {
  if (!folderSupported()) return undefined;
  return (await idb.get<PermissionHandle>("kv", HANDLE_KEY)) ?? undefined;
}

export async function folderState(): Promise<FolderState> {
  if (idb.projectFiles()) return { status: "project", name: "output" };
  if (!folderSupported()) return { status: "unsupported" };
  const handle = await storedHandle();
  if (!handle) return { status: "none" };
  const permission = await handle.queryPermission({ mode: "readwrite" });
  return permission === "granted"
    ? { status: "ready", name: handle.name }
    : { status: "needs-permission", name: handle.name };
}

/** Ask the user for a folder (needs a click). Returns its name, or null when they cancelled. */
export async function pickFolder(): Promise<string | null> {
  if (!window.showDirectoryPicker) throw new Error("Choosing a folder needs Chrome or Edge.");
  let handle: FileSystemDirectoryHandle;
  try {
    handle = await window.showDirectoryPicker({
      id: "ai-job-agent",
      mode: "readwrite",
      startIn: "documents",
    });
  } catch (error) {
    if ((error as DOMException)?.name === "AbortError") return null;
    throw error;
  }
  await idb.put("kv", handle, HANDLE_KEY);
  return handle.name;
}

/** Re-grant access after a browser restart (needs a click). */
export async function reconnectFolder(): Promise<boolean> {
  const handle = await storedHandle();
  if (!handle) return false;
  return (await handle.requestPermission({ mode: "readwrite" })) === "granted";
}

export async function forgetFolder() {
  await idb.remove("kv", HANDLE_KEY);
}

/** The folder when it can be written to right now, otherwise null. */
export async function readyFolder(): Promise<PermissionHandle | null> {
  const handle = await storedHandle();
  if (!handle) return null;
  return (await handle.queryPermission({ mode: "readwrite" })) === "granted" ? handle : null;
}

function parts(path: string) {
  return path.split("/").filter((part) => part && part !== "." && part !== "..");
}

async function directoryFor(root: FileSystemDirectoryHandle, segments: string[], create: boolean) {
  let directory = root;
  for (const segment of segments) directory = await directory.getDirectoryHandle(segment, { create });
  return directory;
}

/** Write a file at a relative path like "CVs/Name_CV_Acme.docx", creating folders as needed. */
export async function writeFile(root: FileSystemDirectoryHandle, path: string, data: Blob | string) {
  const segments = parts(path);
  const name = segments.pop();
  if (!name) throw new Error("Empty file name.");
  const directory = await directoryFor(root, segments, true);
  const file = await directory.getFileHandle(name, { create: true });
  const writable = await file.createWritable();
  try {
    await writable.write(data);
  } finally {
    await writable.close();
  }
}

export async function readFile(root: FileSystemDirectoryHandle, path: string): Promise<File | null> {
  const segments = parts(path);
  const name = segments.pop();
  if (!name) return null;
  try {
    const directory = await directoryFor(root, segments, false);
    return await (await directory.getFileHandle(name)).getFile();
  } catch {
    return null;
  }
}

export async function removeFile(root: FileSystemDirectoryHandle, path: string) {
  const segments = parts(path);
  const name = segments.pop();
  if (!name) return;
  try {
    await (await directoryFor(root, segments, false)).removeEntry(name);
  } catch {
    /* already gone */
  }
}

/** Files directly inside a subfolder: [{ path, file }]. A missing subfolder lists nothing. */
export async function listFiles(root: FileSystemDirectoryHandle, folder: string) {
  const items: { path: string; file: File }[] = [];
  let directory: PermissionHandle;
  try {
    directory = (await root.getDirectoryHandle(folder)) as PermissionHandle;
  } catch {
    return items;
  }
  for await (const entry of directory.values()) {
    if (entry.kind === "file" && !entry.name.startsWith("~$") && !entry.name.startsWith(".")) {
      items.push({ path: `${folder}/${entry.name}`, file: await (entry as FileSystemFileHandle).getFile() });
    }
  }
  return items;
}
