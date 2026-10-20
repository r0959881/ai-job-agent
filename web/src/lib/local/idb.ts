/* A small promise wrapper around IndexedDB. Each signed-in user gets their own database. */

export type StoreName = "jobs" | "documents" | "blobs" | "runs" | "kv";

const VERSION = 1;
let userId: number | null = null;
let projectFilesMode = false;
let opening: Promise<IDBDatabase> | null = null;

/**
 * Called when the session is known; later calls open that user's database.
 * `projectFiles` is the local account on your own PC: documents live in the project's output/.
 */
export function setLocalUser(id: number | null, projectFiles = false) {
  projectFilesMode = Boolean(id) && projectFiles;
  if (id === userId) return;
  userId = id;
  opening?.then((db) => db.close()).catch(() => undefined);
  opening = null;
}

export function localUser() {
  return userId;
}

export function projectFiles() {
  return projectFilesMode;
}

function promisify<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function open(): Promise<IDBDatabase> {
  if (userId == null) return Promise.reject(new Error("Not signed in."));
  if (!opening) {
    const request = indexedDB.open(`ai-job-agent-u${userId}`, VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("jobs")) db.createObjectStore("jobs", { keyPath: "id" });
      if (!db.objectStoreNames.contains("documents")) {
        const docs = db.createObjectStore("documents", { keyPath: "id", autoIncrement: true });
        docs.createIndex("job_id", "job_id");
        docs.createIndex("path", "path");
      }
      if (!db.objectStoreNames.contains("blobs")) db.createObjectStore("blobs", { keyPath: "id" });
      if (!db.objectStoreNames.contains("runs"))
        db.createObjectStore("runs", { keyPath: "id", autoIncrement: true });
      if (!db.objectStoreNames.contains("kv")) db.createObjectStore("kv");
    };
    opening = promisify(request).catch((error) => {
      opening = null;
      throw new Error(
        `This browser's storage is not available (${(error as Error)?.message ?? "blocked"}). ` +
          "Private windows and some privacy settings block it.",
      );
    });
  }
  return opening;
}

async function store(name: StoreName, mode: IDBTransactionMode) {
  const db = await open();
  return db.transaction(name, mode).objectStore(name);
}

export async function getAll<T>(name: StoreName): Promise<T[]> {
  return promisify((await store(name, "readonly")).getAll()) as Promise<T[]>;
}

export async function get<T>(name: StoreName, key: IDBValidKey): Promise<T | undefined> {
  return promisify((await store(name, "readonly")).get(key)) as Promise<T | undefined>;
}

export async function put<T>(name: StoreName, value: T, key?: IDBValidKey): Promise<IDBValidKey> {
  return promisify((await store(name, "readwrite")).put(value, key));
}

export async function remove(name: StoreName, key: IDBValidKey): Promise<void> {
  await promisify((await store(name, "readwrite")).delete(key));
}

export async function clear(name: StoreName): Promise<void> {
  await promisify((await store(name, "readwrite")).clear());
}

/** Write many records in one transaction. */
export async function putMany<T>(name: StoreName, values: T[]): Promise<void> {
  if (!values.length) return;
  const db = await open();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(name, "readwrite");
    const objects = tx.objectStore(name);
    for (const value of values) objects.put(value);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

export async function getByIndex<T>(name: StoreName, index: string, value: IDBValidKey): Promise<T[]> {
  const objects = await store(name, "readonly");
  return promisify(objects.index(index).getAll(value)) as Promise<T[]>;
}
