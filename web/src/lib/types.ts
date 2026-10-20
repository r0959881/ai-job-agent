/* Shapes returned by the server API and by the local store (lib/local). */

export interface PersonalInfo {
  full_name: string;
  headline: string;
  email: string;
  phone: string;
  location: string;
  [extra: string]: string;
}

export interface RoleProfile {
  focus: string;
  keywords: string[];
  preferred_skill_categories: string[];
  preferred_projects: string[];
}

export interface Experience {
  company: string;
  role: string;
  location: string;
  dates: string;
  type: string;
  bullets: string[];
}

export interface Project {
  title: string;
  tech_stack: string;
  highlights: string[];
}

export interface Certification {
  name: string;
  issuer: string;
  year: string;
}

export interface Education {
  degree: string;
  institution: string;
  location: string;
  dates: string;
  coursework: string[];
}

export interface Resume {
  personal_info: PersonalInfo;
  role_profiles: Record<string, RoleProfile>;
  standard_answers: Record<string, string>;
  core_skills: Record<string, string[]>;
  experience: Experience[];
  projects: Project[];
  certifications: Certification[];
  education: Education;
  languages: string[];
}

export interface ResumeResponse {
  data: Resume;
  etag: string;
  warnings: string[];
  empty: boolean;
}

export interface BackupInfo {
  id: string;
  created_at: string;
  size: number;
  label: string;
}

export interface YamlError {
  line: number | null;
  column: number | null;
  message: string;
}

export type MergeStatus = "new" | "matching" | "conflict";
export type MergeAction = "add" | "skip" | "keep_mine" | "use_import" | "keep_both";

export interface MergeItem {
  id: string;
  section: string;
  label: string;
  status: MergeStatus;
  current: unknown;
  imported: unknown;
  changed_fields: string[];
  ai_fields: string[];
  low_confidence: boolean;
}

export interface ImportResult {
  source: "resume_file" | "linkedin";
  draft: Resume;
  items: MergeItem[];
  warnings: string[];
  skills_pool: string[];
  skill_suggestions: Record<string, string>;
  education_alternatives: Education[];
  preview_html?: string | null;
  low_confidence: string[];
  ai_used: boolean;
  current_empty: boolean;
}

export interface SearchSettings {
  target_roles: Record<string, string[]>;
  extra_keywords: string[];
  search_queries: Record<string, string[]>;
  entry_level_keywords: string[];
  exclude_title_keywords: string[];
  allowed_locations: string[];
  blocked_locations: string[];
  trusted_alert_sources: string[];
  time_window_hours: number;
  regions: string[];
  languages: string[];
  sources: Record<string, boolean>;
  scraping: { results_per_search: number; linkedin_descriptions: boolean; proxies: string[] };
  company_boards: string[];
  adzuna: { country: string; location: string; results_per_page: number };
  gmail?: { senders: string[]; lookback_days: number; max_results: number };
  cover_letters: Record<string, { opening: string; evidence: string; fit: string; closing: string }>;
  alerts?: { smtp_enabled: boolean };
}

export interface SettingsResponse {
  settings: SearchSettings;
  warnings: string[];
}

export type HealthLevel = "ok" | "warning" | "error" | "missing";

export interface IntegrationHealth {
  status: HealthLevel;
  message: string;
  action?: string;
}

export interface IntegrationsStatus {
  groq: IntegrationHealth;
  adzuna: IntegrationHealth;
}

export interface SecretField {
  key: string;
  label: string;
  group: string;
  set: boolean;
  masked: string;
}

export type RunStatus = "running" | "succeeded" | "failed" | "cancelled";
export type StepStatus = "pending" | "running" | "succeeded" | "warning" | "failed" | "skipped";

export interface RunStep {
  step: string;
  label: string;
  status: StepStatus;
  message: string;
  started_at: string | null;
  finished_at: string | null;
  data: Record<string, unknown>;
}

export interface RunOptions {
  sources: string[];
  regions: string[];
  roles: string[];
  /** Empty means any language. */
  languages: string[];
  time_window_hours: number;
  max_tailor: number | null;
  dry_run: boolean;
}

export interface Run {
  id: number;
  started_at: string;
  finished_at: string;
  status: RunStatus;
  discovered: number;
  new: number;
  filtered: number;
  tailored: number;
  failed: number;
  error: string;
  log_path: string;
  options: Partial<RunOptions>;
  summary: {
    eligible?: number;
    failures?: { job_id: string; title: string; reason: string }[];
    report_path?: string;
    sources?: Record<string, unknown>;
  };
  duration_seconds: number | null;
  steps?: RunStep[];
  documents?: DocumentItem[];
}

export interface RunEvent {
  seq: number;
  ts: string;
  step: string | null;
  status: string;
  message: string;
  data: Record<string, unknown>;
}

export type ApplicationStatus = "not_applied" | "applied" | "interviewing" | "offer" | "rejected" | "skipped";

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  source: string;
  status: string;
  description: string;
  category: string;
  contract_type: string;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  posted_at: string;
  discovered_at: string;
  cv_path: string;
  cover_letter_path: string;
  role_family: string;
  application_status: ApplicationStatus;
  applied_at: string;
  notes: string;
  follow_up_at: string;
  apply_checklist: Record<string, boolean>;
  has_cv: boolean;
  eligible?: boolean;
  /** When a run last returned this job (it may have been added much earlier). */
  last_seen_at?: string;
  /** The run that last returned it. */
  last_run_id?: number | null;
}

export interface JobDetail extends Job {
  documents: DocumentItem[];
  matched_keywords: string[];
  missing_keywords: string[];
  tips: string[];
  history: { at: string; text: string }[];
}

export interface JobsPage {
  items: Job[];
  total: number;
  page: number;
  page_size: number;
  facets: { sources: string[]; role_families: string[] };
}

export type DocumentKind = "cv" | "cover_letter" | "report" | "other";

export interface DocumentItem {
  id: number;
  job_id: string | null;
  kind: DocumentKind;
  role_family: string;
  path: string;
  name: string;
  created_at: string;
  run_id: number | null;
  size: number;
  exists: boolean;
  job_title?: string | null;
  job_company?: string | null;
}

export interface TailoredContent {
  summary: string;
  bullets: string[];
  role_family: string;
}

export interface Stats {
  jobs_last_window: number;
  window_hours: number;
  cvs_generated: number;
  applications_sent: number;
  interviews: number;
  funnel: { key: string; label: string; count: number }[];
  last_run: Run | null;
  ready_to_apply: Job[];
  integrations: IntegrationsStatus;
}

export interface Region {
  id: string;
  label: string;
  group: string;
  flag: string;
}

export interface JobLanguage {
  id: string;
  label: string;
}

export interface SearchRole {
  name: string;
  focus: string;
  has_profile: boolean;
  keywords: string[];
  queries: string[];
  searches_by_name: boolean;
}

export type SourceKind = "scraper" | "api" | "email";

export interface SearchSource {
  key: string;
  label: string;
  kind: SourceKind;
  description: string;
  default: boolean;
  configured: boolean;
  setup_hint: string;
  regions: string[];
}

export interface SearchCatalog {
  regions: Region[];
  groups: string[];
  languages: JobLanguage[];
  roles: SearchRole[];
  sources: SearchSource[];
  defaults: { regions: string[]; roles: string[]; languages: string[]; time_window_hours: number };
}
