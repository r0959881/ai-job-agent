/** Minimal line diff (LCS) for comparing resume backups with the current file. */
export type DiffLine = { type: "same" | "add" | "remove"; text: string; oldLine?: number; newLine?: number };

export function diffLines(oldText: string, newText: string): DiffLine[] {
  // A missing final newline is not a meaningful change.
  const a = oldText.replace(/\r\n/g, "\n").replace(/\n+$/, "").split("\n");
  const b = newText.replace(/\r\n/g, "\n").replace(/\n+$/, "").split("\n");
  const n = a.length;
  const m = b.length;
  // Lengths of the longest common subsequence from (i, j) to the end.
  const lcs: Uint32Array[] = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ type: "same", text: a[i], oldLine: i + 1, newLine: j + 1 });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      out.push({ type: "remove", text: a[i], oldLine: i + 1 });
      i++;
    } else {
      out.push({ type: "add", text: b[j], newLine: j + 1 });
      j++;
    }
  }
  while (i < n) out.push({ type: "remove", text: a[i], oldLine: ++i });
  while (j < m) out.push({ type: "add", text: b[j], newLine: ++j });
  return out;
}

/** Collapse long unchanged runs, keeping `context` lines around each change. */
export function withContext(lines: DiffLine[], context = 3): (DiffLine | { type: "gap"; count: number })[] {
  const keep = new Array(lines.length).fill(false);
  lines.forEach((line, index) => {
    if (line.type !== "same") {
      for (let k = Math.max(0, index - context); k <= Math.min(lines.length - 1, index + context); k++) keep[k] = true;
    }
  });
  const out: (DiffLine | { type: "gap"; count: number })[] = [];
  let gap = 0;
  lines.forEach((line, index) => {
    if (keep[index]) {
      if (gap) out.push({ type: "gap", count: gap });
      gap = 0;
      out.push(line);
    } else gap++;
  });
  if (gap) out.push({ type: "gap", count: gap });
  return out;
}
