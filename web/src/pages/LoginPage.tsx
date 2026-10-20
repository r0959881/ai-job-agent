import { useQueryClient } from "@tanstack/react-query";
import { BriefcaseBusiness, FolderLock, ShieldCheck } from "lucide-react";
import * as React from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { Field } from "@/components/common";
import { ErrorState, SkeletonRows } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, Input } from "@/components/ui/primitives";
import { serverRequest } from "@/lib/api";
import { sessionKey, useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path
        fill="#4285F4"
        d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.6v3h3.9c2.2-2.1 3.5-5.1 3.5-8.8z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3c-1.1.7-2.5 1.2-4.1 1.2-3.1 0-5.8-2.1-6.7-5H1.3v3.1A12 12 0 0 0 12 24z"
      />
      <path fill="#FBBC05" d="M5.3 14.3a7.2 7.2 0 0 1 0-4.6V6.6H1.3a12 12 0 0 0 0 10.8l4-3.1z" />
      <path
        fill="#EA4335"
        d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.3 6.6l4 3.1c.9-2.9 3.6-4.9 6.7-4.9z"
      />
    </svg>
  );
}

function LinkedInMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path
        fill="#0A66C2"
        d="M20.4 20.5h-3.6v-5.6c0-1.3 0-3-1.8-3s-2.1 1.4-2.1 2.9v5.7H9.3V9h3.4v1.6h.1c.5-.9 1.6-1.8 3.4-1.8 3.6 0 4.3 2.4 4.3 5.5v6.2zM5.3 7.4a2.1 2.1 0 1 1 0-4.2 2.1 2.1 0 0 1 0 4.2zM7.1 20.5H3.6V9h3.5v11.5zM22.2 0H1.8C.8 0 0 .8 0 1.7v20.6c0 .9.8 1.7 1.8 1.7h20.4c1 0 1.8-.8 1.8-1.7V1.7C24 .8 23.2 0 22.2 0z"
      />
    </svg>
  );
}

const MARKS: Record<string, React.ReactNode> = { google: <GoogleMark />, linkedin: <LinkedInMark /> };

function safeNext(value: string | null) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/";
}

function DevSignIn({ next }: { next: string }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  return (
    <form
      className="space-y-3 border-t pt-4"
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");
        try {
          await serverRequest("POST", "/api/auth/dev/login", { email, name: email.split("@")[0] });
          await queryClient.invalidateQueries({ queryKey: sessionKey });
          window.location.assign(next);
        } catch (exc) {
          setError((exc as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <Field label="Developer sign-in (local only)" htmlFor="dev-email" error={error || undefined}>
        <Input
          id="dev-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </Field>
      <Button type="submit" variant="outline" className="w-full" loading={busy}>
        Sign in without a provider
      </Button>
    </form>
  );
}

export default function LoginPage() {
  const session = useSession();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const error = params.get("error");

  if (session.isPending) return <SkeletonRows className="p-8" rows={4} />;
  if (session.isError)
    return (
      <ErrorState
        title="Could not reach the server"
        error={session.error}
        onRetry={() => session.refetch()}
      />
    );
  if (session.data.user) return <Navigate to={next} replace />;
  const providers = session.data.providers;
  const oauth = providers.filter((provider) => provider.id !== "dev" && provider.id !== "local");
  const local = providers.find((provider) => provider.id === "local");

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-md space-y-6 p-6 sm:p-8">
        <div className="space-y-2 text-center">
          <div className="mx-auto flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <BriefcaseBusiness className="size-5" aria-hidden />
          </div>
          <h1 className="text-title font-semibold">AI Job Agent</h1>
          <p className="text-body text-muted-foreground">
            Finds jobs that fit your profile and writes a tailored CV for each one.
          </p>
        </div>

        {error && (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-body text-danger">
            {error}
          </p>
        )}

        <div className="space-y-2">
          {local && (
            <Button
              size="lg"
              className="w-full"
              onClick={async () => {
                await serverRequest("POST", "/api/auth/local/login");
                window.location.assign(next);
              }}
            >
              Continue with the local account
            </Button>
          )}
          {oauth.map((provider) => (
            <a
              key={provider.id}
              href={`/api/auth/${provider.id}/login?next=${encodeURIComponent(next)}`}
              className={cn(buttonVariants({ variant: "outline", size: "lg" }), "w-full gap-3")}
            >
              {MARKS[provider.id]}
              Continue with {provider.label}
            </a>
          ))}
          {!oauth.length && !local && !providers.some((p) => p.id === "dev") && (
            <p className="text-center text-body text-muted-foreground">
              Sign-in is not set up on this server yet. The administrator needs to add the Google or LinkedIn
              keys.
            </p>
          )}
        </div>
        {providers.some((provider) => provider.id === "dev") && <DevSignIn next={next} />}

        <ul className="space-y-2 text-caption text-muted-foreground">
          <li className="flex gap-2">
            <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
            Sign-in shares only your name, email and photo. Your profile and search preferences are saved to
            your account.
          </li>
          <li className="flex gap-2">
            <FolderLock className="mt-0.5 size-4 shrink-0" aria-hidden />
            Jobs, CVs and cover letters stay on your computer, in a folder you choose.
          </li>
        </ul>
      </Card>
    </main>
  );
}
