import { cn, formatRelative, formatSalary } from "@/lib/utils";

describe("cn", () => {
  it("keeps a text colour next to the custom font sizes", () => {
    expect(cn("text-primary-foreground", "text-caption")).toBe("text-primary-foreground text-caption");
    expect(cn("text-body", "text-caption")).toBe("text-caption");
  });
});

describe("formatters", () => {
  it("formats relative times", () => {
    const now = Date.parse("2026-10-19T12:00:00Z");
    expect(formatRelative("2026-10-19T09:00:00Z", now)).toBe("3h ago");
    expect(formatRelative("2026-10-19 11:59:50", now)).toBe("just now");
  });
  it("formats salary ranges", () => {
    expect(formatSalary(3200, 4100, "€")).toBe("€3.200–4.100"); // Belgian grouping
    expect(formatSalary(null, null, "")).toBe("");
  });
});
