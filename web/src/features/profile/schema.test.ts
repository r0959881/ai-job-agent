import { countChanges, fromForm, profileSchema, toForm } from "@/features/profile/schema";
import type { Resume } from "@/lib/types";

const resume: Resume = {
  personal_info: { full_name: "Ada Lovelace", headline: "Analyst", email: "ada@example.com", phone: "", location: "" },
  role_profiles: {
    "Data Analyst": { focus: "SQL", keywords: ["SQL"], preferred_skill_categories: ["bi"], preferred_projects: [] },
  },
  standard_answers: { notice_period: "2 weeks" },
  core_skills: { bi: ["Power BI"], languages: ["SQL", "Python"] },
  experience: [{ company: "Acme", role: "Analyst", location: "", dates: "2025", type: "", bullets: ["Did things"] }],
  projects: [{ title: "Dashboards", tech_stack: "Power BI", highlights: [] }],
  certifications: [],
  education: { degree: "BSc", institution: "Uni", location: "", dates: "", coursework: [] },
  languages: ["English: C2"],
};

describe("profile form conversion", () => {
  it("round-trips the resume shape, keeping map order", () => {
    const back = fromForm(toForm(resume));
    expect(back).toEqual(resume);
    expect(Object.keys(back.core_skills)).toEqual(["bi", "languages"]);
  });

  it("keeps unknown keys", () => {
    const withExtra = { ...resume, experience: [{ ...resume.experience[0], team_size: "4" }] } as unknown as Resume;
    expect((fromForm(toForm(withExtra)).experience[0] as unknown as Record<string, string>).team_size).toBe("4");
  });

  it("validates required fields and duplicate names", () => {
    const form = toForm(resume);
    form.experience[0].company = "";
    form.core_skills.push({ name: "BI", skills: [] });
    form.personal_info.email = "nope";
    const result = profileSchema.safeParse(form);
    expect(result.success).toBe(false);
    const messages = result.success ? [] : result.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`);
    expect(messages).toContain("experience.0.company: Company is required");
    expect(messages).toContain("core_skills.2.name: This name is used twice");
    expect(messages.some((m) => m.startsWith("personal_info.email"))).toBe(true);
  });

  it("counts changed leaves", () => {
    const a = toForm(resume);
    const b = structuredClone(a);
    b.personal_info.headline = "Engineer";
    b.experience[0].bullets.push("New");
    expect(countChanges(a, a)).toBe(0);
    expect(countChanges(a, b)).toBe(2);
  });
});
