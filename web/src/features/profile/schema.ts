import { z } from "zod";
import type { Resume } from "@/lib/types";

/*
 * The editor works on a form-friendly shape: maps keyed by name (role profiles,
 * skill categories, standard answers) become ordered arrays so they can be
 * renamed and reordered. Unknown keys are kept with .passthrough().
 */

const required = (label: string) => z.string().trim().min(1, `${label} is required`);
const stringList = z.array(z.string());

export const personalInfoSchema = z
  .object({
    full_name: required("Full name"),
    headline: z.string(),
    email: z
      .string()
      .trim()
      .refine((v) => !v || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v), "Enter a valid email address, like name@example.com"),
    phone: z.string(),
    location: z.string(),
  })
  .passthrough();

export const roleProfileSchema = z
  .object({
    name: required("Role name"),
    focus: z.string(),
    keywords: stringList,
    preferred_skill_categories: stringList,
    preferred_projects: stringList,
  })
  .passthrough();

export const experienceSchema = z
  .object({
    company: required("Company"),
    role: required("Role"),
    location: z.string(),
    dates: z.string(),
    type: z.string(),
    bullets: stringList,
  })
  .passthrough();

export const projectSchema = z
  .object({ title: required("Title"), tech_stack: z.string(), highlights: stringList })
  .passthrough();

export const certificationSchema = z
  .object({ name: required("Name"), issuer: z.string(), year: z.string() })
  .passthrough();

export const educationSchema = z
  .object({
    degree: z.string(),
    institution: z.string(),
    location: z.string(),
    dates: z.string(),
    coursework: stringList,
  })
  .passthrough();

function uniqueNames<T>(items: T[], pick: (item: T) => string, ctx: z.RefinementCtx, path: string, field: string) {
  const seen = new Map<string, number>();
  items.forEach((item, index) => {
    const key = pick(item).trim().toLowerCase();
    if (!key) return;
    if (seen.has(key)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "This name is used twice", path: [path, index, field] });
    } else seen.set(key, index);
  });
}

export const profileSchema = z
  .object({
    personal_info: personalInfoSchema,
    role_profiles: z.array(roleProfileSchema),
    standard_answers: z.array(z.object({ key: required("Question"), value: z.string() })),
    core_skills: z.array(z.object({ name: required("Category name"), skills: stringList })),
    experience: z.array(experienceSchema),
    projects: z.array(projectSchema),
    certifications: z.array(certificationSchema),
    education: educationSchema,
    languages: z.array(z.object({ value: z.string().trim().min(1, "Enter a language or remove this row") })),
  })
  .superRefine((value, ctx) => {
    uniqueNames(value.role_profiles, (r) => r.name, ctx, "role_profiles", "name");
    uniqueNames(value.core_skills, (c) => c.name, ctx, "core_skills", "name");
    uniqueNames(value.standard_answers, (a) => a.key, ctx, "standard_answers", "key");
    uniqueNames(value.projects, (p) => p.title, ctx, "projects", "title");
  });

export type ProfileForm = z.infer<typeof profileSchema>;
export type ExperienceForm = z.infer<typeof experienceSchema>;
export type ProjectForm = z.infer<typeof projectSchema>;
export type CertificationForm = z.infer<typeof certificationSchema>;

export const emptyExperience = (): ExperienceForm => ({
  company: "",
  role: "",
  location: "",
  dates: "",
  type: "",
  bullets: [],
});
export const emptyProject = (): ProjectForm => ({ title: "", tech_stack: "", highlights: [] });
export const emptyCertification = (): CertificationForm => ({ name: "", issuer: "", year: "" });

export function toForm(resume: Resume): ProfileForm {
  return {
    personal_info: {
      ...resume.personal_info,
      full_name: resume.personal_info?.full_name ?? "",
      headline: resume.personal_info?.headline ?? "",
      email: resume.personal_info?.email ?? "",
      phone: resume.personal_info?.phone ?? "",
      location: resume.personal_info?.location ?? "",
    },
    role_profiles: Object.entries(resume.role_profiles ?? {}).map(([name, profile]) => ({
      ...profile,
      name,
      focus: profile.focus ?? "",
      keywords: profile.keywords ?? [],
      preferred_skill_categories: profile.preferred_skill_categories ?? [],
      preferred_projects: profile.preferred_projects ?? [],
    })),
    standard_answers: Object.entries(resume.standard_answers ?? {}).map(([key, value]) => ({ key, value })),
    core_skills: Object.entries(resume.core_skills ?? {}).map(([name, skills]) => ({ name, skills })),
    experience: (resume.experience ?? []).map((e) => ({ ...emptyExperience(), ...e })),
    projects: (resume.projects ?? []).map((p) => ({ ...emptyProject(), ...p })),
    certifications: (resume.certifications ?? []).map((c) => ({ ...emptyCertification(), ...c })),
    education: {
      ...resume.education,
      degree: resume.education?.degree ?? "",
      institution: resume.education?.institution ?? "",
      location: resume.education?.location ?? "",
      dates: resume.education?.dates ?? "",
      coursework: resume.education?.coursework ?? [],
    },
    languages: (resume.languages ?? []).map((value) => ({ value })),
  };
}

export function fromForm(form: ProfileForm): Resume {
  return {
    personal_info: form.personal_info as Resume["personal_info"],
    role_profiles: Object.fromEntries(
      form.role_profiles.map(({ name, ...profile }) => [name.trim(), profile as Resume["role_profiles"][string]]),
    ),
    standard_answers: Object.fromEntries(form.standard_answers.map(({ key, value }) => [key.trim(), value])),
    core_skills: Object.fromEntries(form.core_skills.map(({ name, skills }) => [name.trim(), skills])),
    experience: form.experience as Resume["experience"],
    projects: form.projects as Resume["projects"],
    certifications: form.certifications as Resume["certifications"],
    education: form.education as Resume["education"],
    languages: form.languages.map((l) => l.value),
  };
}

/** Number of leaf values that differ between two form states (for the save bar). */
export function countChanges(a: unknown, b: unknown): number {
  if (a === b) return 0;
  if (Array.isArray(a) && Array.isArray(b)) {
    let count = Math.abs(a.length - b.length);
    for (let i = 0; i < Math.min(a.length, b.length); i++) count += countChanges(a[i], b[i]);
    return count;
  }
  if (a && b && typeof a === "object" && typeof b === "object") {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    let count = 0;
    for (const key of keys) count += countChanges((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key]);
    return count;
  }
  return (a ?? "") === (b ?? "") ? 0 : 1;
}

export const SECTIONS = [
  { id: "personal", label: "Personal info", field: "personal_info" },
  { id: "role-profiles", label: "Role profiles", field: "role_profiles" },
  { id: "skills", label: "Skills", field: "core_skills" },
  { id: "experience", label: "Experience", field: "experience" },
  { id: "projects", label: "Projects", field: "projects" },
  { id: "education", label: "Education", field: "education" },
  { id: "certifications", label: "Certifications", field: "certifications" },
  { id: "languages", label: "Languages", field: "languages" },
  { id: "answers", label: "Standard answers", field: "standard_answers" },
] as const;

export function humanize(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
