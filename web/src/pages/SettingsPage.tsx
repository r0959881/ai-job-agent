import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Linkedin, LogOut, Trash2, UserRound } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { PageHeader } from "@/components/common";
import { useConfirm } from "@/components/confirm";
import { Button, buttonVariants } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/controls";
import { Card } from "@/components/ui/primitives";
import { SearchSettingsForm } from "@/features/settings/SearchSettingsForm";
import { SecretsPanel } from "@/features/settings/SecretsPanel";
import { StorageCard } from "@/features/settings/StorageCard";
import { api, serverRequest } from "@/lib/api";
import { useSession, useSignOut, useUser } from "@/lib/session";

const TABS = ["search", "integrations", "linkedin", "storage", "account"] as const;

function LinkedInPanel() {
  return (
    <div className="max-w-3xl space-y-4">
      <Card className="space-y-3 p-4">
        <h3 className="text-section">Import your profile</h3>
        <p className="max-w-prose text-body text-muted-foreground">
          Signing in with LinkedIn only shares your name, email and photo: LinkedIn does not give apps your
          work history. To bring in your positions, education, skills, certifications and languages, download
          your LinkedIn data export and import it here. You review every change before it touches your
          profile.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link className={buttonVariants()} to="/onboarding?source=linkedin&return=/settings/linkedin">
            <Linkedin /> Import profile from LinkedIn export
          </Link>
          <a
            className={buttonVariants({ variant: "outline" })}
            href="https://www.linkedin.com/mypreferences/d/download-my-data"
            target="_blank"
            rel="noopener noreferrer"
          >
            Request your LinkedIn data export
          </a>
        </div>
      </Card>
      <Card className="space-y-2 p-4">
        <h3 className="text-section">LinkedIn job search</h3>
        <p className="max-w-prose text-body text-muted-foreground">
          Runs search LinkedIn's public job listings directly (the LinkedIn source in Start run). If LinkedIn
          starts refusing searches, lower “Results per search” in the Search tab or run less often.
        </p>
      </Card>
    </div>
  );
}

function StoragePanel() {
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const reset = useMutation({
    mutationFn: () => api.post<{ deleted: number }>("/api/data/reset-jobs", { confirm: "RESET" }),
    onSuccess: (result) => {
      toast.success(`Deleted ${result.deleted} job(s)`, {
        description: "Your profile, settings and files were kept.",
      });
      queryClient.invalidateQueries();
    },
    onError: (error: Error) => toast.error("Reset failed", { description: error.message }),
  });
  return (
    <div className="max-w-3xl space-y-4">
      <StorageCard />
      <Card className="flex flex-wrap items-center gap-3 border-danger/30 p-4">
        <div className="flex-1">
          <h3 className="text-section text-danger">Clear the job list</h3>
          <p className="text-body text-muted-foreground">
            Deletes every job and its application tracking from this device. Your profile, settings, run
            history and files stay.
          </p>
        </div>
        <Button
          variant="danger"
          loading={reset.isPending}
          onClick={async () => {
            const ok = await confirm({
              title: "Clear the job list?",
              description:
                "Every job, status, note and follow-up date on this device is deleted. This cannot be undone. Download the job list first if you want a copy.",
              confirmLabel: "Delete all jobs",
              destructive: true,
              typeToConfirm: "RESET",
            });
            if (ok) reset.mutate();
          }}
        >
          <Trash2 /> Clear jobs
        </Button>
      </Card>
    </div>
  );
}

function AccountPanel() {
  const user = useUser();
  const projectFiles = Boolean(useSession().data?.project_files);
  const confirm = useConfirm();
  const signOut = useSignOut();
  const remove = useMutation({
    mutationFn: () => serverRequest("POST", "/api/account/delete", { confirm: "DELETE" }),
    onSuccess: () => {
      toast.success("Your account was deleted");
      window.location.assign("/login");
    },
    onError: (error: Error) => toast.error("The account was not deleted", { description: error.message }),
  });
  return (
    <div className="max-w-3xl space-y-4">
      <Card className="flex flex-wrap items-center gap-4 p-4">
        {user.picture ? (
          <img src={user.picture} alt="" className="size-12 rounded-full" referrerPolicy="no-referrer" />
        ) : (
          <span className="flex size-12 items-center justify-center rounded-full bg-muted">
            <UserRound className="size-6 text-muted-foreground" aria-hidden />
          </span>
        )}
        <div className="flex-1">
          <p className="font-medium">{user.name || user.email}</p>
          <p className="text-body text-muted-foreground">
            {user.email}
            {user.providers.length > 0 &&
              ` · signed in with ${user.providers.map((p) => p[0].toUpperCase() + p.slice(1)).join(" and ")}`}
          </p>
        </div>
        <Button variant="outline" onClick={signOut}>
          <LogOut /> Sign out
        </Button>
      </Card>
      <Card className="flex flex-wrap items-center gap-3 p-4">
        <div className="flex-1">
          <h3 className="text-section">Export your account</h3>
          <p className="text-body text-muted-foreground">
            Everything the server keeps about you: your profile with its history and your search settings, as
            JSON. API keys are never included.
          </p>
        </div>
        <a className={buttonVariants({ variant: "outline" })} href="/api/account/export">
          <Download /> Download
        </a>
      </Card>
      {projectFiles ? (
        <p className="text-caption text-muted-foreground">
          This is the local account on this PC. It uses the project&apos;s own files, so it cannot be deleted
          here. Sign out to try another account with the developer sign-in.
        </p>
      ) : (
        <Card className="flex flex-wrap items-center gap-3 border-danger/30 p-4">
          <div className="flex-1">
            <h3 className="text-section text-danger">Delete your account</h3>
            <p className="text-body text-muted-foreground">
              Removes your profile, settings and API keys from the server. Files in your documents folder are
              not touched.
            </p>
          </div>
          <Button
            variant="danger"
            loading={remove.isPending}
            onClick={async () => {
              const ok = await confirm({
                title: "Delete your account?",
                description:
                  "Your profile, its history, your settings and your API keys are deleted from the server. This cannot be undone.",
                confirmLabel: "Delete my account",
                destructive: true,
                typeToConfirm: "DELETE",
              });
              if (ok) remove.mutate();
            }}
          >
            <Trash2 /> Delete account
          </Button>
        </Card>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const { tab = "search" } = useParams();
  const navigate = useNavigate();
  const active = (TABS as readonly string[]).includes(tab) ? tab : "search";
  return (
    <>
      <PageHeader
        title="Settings"
        description="What the agent searches for, your API keys, where files go, and your account."
      />
      <Tabs value={active} onValueChange={(value) => navigate(`/settings/${value}`, { replace: true })}>
        <TabsList>
          <TabsTrigger value="search">Search</TabsTrigger>
          <TabsTrigger value="integrations">Integrations</TabsTrigger>
          <TabsTrigger value="linkedin">LinkedIn</TabsTrigger>
          <TabsTrigger value="storage">Storage</TabsTrigger>
          <TabsTrigger value="account">Account</TabsTrigger>
        </TabsList>
        <TabsContent value="search">
          <SearchSettingsForm />
        </TabsContent>
        <TabsContent value="integrations">
          <div className="max-w-3xl">
            <SecretsPanel />
          </div>
        </TabsContent>
        <TabsContent value="linkedin">
          <LinkedInPanel />
        </TabsContent>
        <TabsContent value="storage">
          <StoragePanel />
        </TabsContent>
        <TabsContent value="account">
          <AccountPanel />
        </TabsContent>
      </Tabs>
    </>
  );
}
