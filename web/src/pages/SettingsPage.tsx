import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, FolderOpen, Linkedin, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/common";
import { useConfirm } from "@/components/confirm";
import { Button, buttonVariants } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/controls";
import { Card } from "@/components/ui/primitives";
import { GmailCard, useGmailRedirectToast } from "@/features/settings/GmailCard";
import { SearchSettingsForm } from "@/features/settings/SearchSettingsForm";
import { SecretsPanel } from "@/features/settings/SecretsPanel";
import { api } from "@/lib/api";

const TABS = ["search", "integrations", "linkedin", "data"] as const;

function LinkedInPanel() {
  return (
    <div className="max-w-3xl space-y-4">
      <Card className="space-y-3 p-4">
        <h3 className="text-section">LinkedIn jobs come through Gmail</h3>
        <p className="max-w-prose text-body text-muted-foreground">
          LinkedIn has no personal API for job listings. Instead, create LinkedIn job alerts (for example “Junior Data
          Engineer” in Belgium, daily). The alert emails arrive in Gmail, and each run reads them when Gmail is connected.
        </p>
        <div className="flex flex-wrap gap-2">
          <a className={buttonVariants({ variant: "outline" })} href="https://www.linkedin.com/jobs/" target="_blank" rel="noopener noreferrer">
            LinkedIn Jobs (create an alert) <ExternalLink />
          </a>
          <Link className={buttonVariants({ variant: "ghost" })} to="/settings/integrations#gmail">
            Check the Gmail connection
          </Link>
        </div>
      </Card>
      <Card className="space-y-3 p-4">
        <h3 className="text-section">Import your profile</h3>
        <p className="max-w-prose text-body text-muted-foreground">
          Bring your positions, education, skills, certifications and languages in from LinkedIn's data export. You review
          every change before it touches your profile.
        </p>
        <Link className={buttonVariants()} to="/onboarding?source=linkedin&return=/settings/linkedin">
          <Linkedin /> Import profile from LinkedIn export
        </Link>
      </Card>
    </div>
  );
}

function DataPanel() {
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const open = useMutation({
    mutationFn: () => api.post("/api/data/open-output"),
    onSuccess: () => toast.success("Opened the output folder"),
    onError: (error: Error) => toast.error("Could not open the folder", { description: error.message }),
  });
  const reset = useMutation({
    mutationFn: () => api.post<{ deleted: number }>("/api/data/reset-jobs", { confirm: "RESET" }),
    onSuccess: (result) => {
      toast.success(`Deleted ${result.deleted} job(s)`, { description: "Your resume, settings and files were kept." });
      queryClient.invalidateQueries();
    },
    onError: (error: Error) => toast.error("Reset failed", { description: error.message }),
  });
  return (
    <div className="max-w-3xl space-y-4">
      <Card className="flex flex-wrap items-center gap-3 p-4">
        <div className="flex-1">
          <h3 className="text-section">Output folder</h3>
          <p className="text-body text-muted-foreground">All generated CVs, cover letters, reports and run logs.</p>
        </div>
        <Button variant="outline" onClick={() => open.mutate()} loading={open.isPending}>
          <FolderOpen /> Open folder
        </Button>
      </Card>
      <Card className="flex flex-wrap items-center gap-3 p-4">
        <div className="flex-1">
          <h3 className="text-section">Export everything</h3>
          <p className="text-body text-muted-foreground">A .zip of resume_data.yaml, agent_settings.yaml, jobs.db and output/. API keys and Google tokens are never included.</p>
        </div>
        <a className={buttonVariants({ variant: "outline" })} href="/api/data/export">
          <Download /> Download export
        </a>
      </Card>
      <Card className="flex flex-wrap items-center gap-3 border-danger/30 p-4">
        <div className="flex-1">
          <h3 className="text-section text-danger">Reset the jobs database</h3>
          <p className="text-body text-muted-foreground">Deletes every job and its application tracking. Your resume, settings, run history and files stay.</p>
        </div>
        <Button
          variant="danger"
          loading={reset.isPending}
          onClick={async () => {
            const ok = await confirm({
              title: "Reset the jobs database?",
              description: "Every job, status, note and follow-up date is deleted. This cannot be undone. Export first if you want a copy.",
              confirmLabel: "Delete all jobs",
              destructive: true,
              typeToConfirm: "RESET",
            });
            if (ok) reset.mutate();
          }}
        >
          <Trash2 /> Reset jobs
        </Button>
      </Card>
    </div>
  );
}

export default function SettingsPage() {
  const { tab = "search" } = useParams();
  const navigate = useNavigate();
  useGmailRedirectToast();
  const active = (TABS as readonly string[]).includes(tab) ? tab : "search";
  return (
    <>
      <PageHeader title="Settings" description="What the agent searches for, the services it uses, and your data." />
      <Tabs value={active} onValueChange={(value) => navigate(`/settings/${value}`, { replace: true })}>
        <TabsList>
          <TabsTrigger value="search">Search</TabsTrigger>
          <TabsTrigger value="integrations">Integrations</TabsTrigger>
          <TabsTrigger value="linkedin">LinkedIn</TabsTrigger>
          <TabsTrigger value="data">Data</TabsTrigger>
        </TabsList>
        <TabsContent value="search">
          <SearchSettingsForm />
        </TabsContent>
        <TabsContent value="integrations">
          <div className="grid max-w-5xl gap-6 xl:grid-cols-2">
            <SecretsPanel />
            <div><GmailCard /></div>
          </div>
        </TabsContent>
        <TabsContent value="linkedin">
          <LinkedInPanel />
        </TabsContent>
        <TabsContent value="data">
          <DataPanel />
        </TabsContent>
      </Tabs>
    </>
  );
}
