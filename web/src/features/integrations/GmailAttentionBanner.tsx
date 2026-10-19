import { MailWarning } from "lucide-react";
import { Link } from "react-router-dom";
import { buttonVariants } from "@/components/ui/button";
import { useGmailStatus } from "@/lib/queries";
import { cn } from "@/lib/utils";

/** Shown on the dashboard and in the start-run dialog whenever Gmail needs attention. */
export function GmailAttentionBanner({ compact = false }: { compact?: boolean }) {
  const { data } = useGmailStatus();
  if (
    !data ||
    data.state === "connected" ||
    (data.state === "not_connected" && compact && !data.credentials_present)
  )
    return null;
  const reauth = data.state === "reauth_required";
  const title = reauth
    ? "Gmail needs to be reconnected"
    : data.state === "error"
      ? "Gmail has a problem"
      : "Gmail is not connected";
  const text = reauth
    ? "Google stopped accepting the saved sign-in, so runs skip Gmail alerts until you reconnect."
    : data.state === "error"
      ? data.reason || "The last Gmail check failed."
      : "Connect Gmail to include LinkedIn, Indeed and other alert emails in runs.";
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-warning/30 bg-warning-soft p-3 sm:flex-row sm:items-center",
        !compact && "mb-6",
      )}
    >
      <MailWarning className="size-5 shrink-0 text-warning" aria-hidden />
      <div className="flex-1">
        <p className="font-medium text-warning">{title}</p>
        <p className="text-body text-foreground/80">{text}</p>
      </div>
      <Link to="/settings/integrations#gmail" className={buttonVariants({ size: "sm", variant: "outline" })}>
        {reauth ? "Reconnect Gmail" : "Connect Gmail"}
      </Link>
    </div>
  );
}
