import { diffLines, withContext } from "@/lib/diff";

describe("diffLines", () => {
  it("marks added and removed lines", () => {
    const result = diffLines("a\nb\nc", "a\nB\nc\nd");
    expect(result.map((l) => `${l.type}:${l.text}`)).toEqual([
      "same:a",
      "remove:b",
      "add:B",
      "same:c",
      "add:d",
    ]);
  });

  it("ignores a missing trailing newline and CRLF", () => {
    expect(diffLines("a\r\nb\r\n", "a\nb").every((l) => l.type === "same")).toBe(true);
  });

  it("collapses unchanged runs around changes", () => {
    const old = Array.from({ length: 20 }, (_, i) => `line ${i}`).join("\n");
    const changed = old.replace("line 10", "LINE 10");
    const collapsed = withContext(diffLines(old, changed), 2);
    expect(collapsed[0]).toEqual({ type: "gap", count: 8 });
    expect(collapsed.filter((l) => l.type === "add")).toHaveLength(1);
    expect(collapsed.at(-1)).toEqual({ type: "gap", count: 7 });
  });
});
