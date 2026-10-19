import { Compass } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/states";
import { buttonVariants } from "@/components/ui/button";

export default function NotFoundPage() {
  return (
    <EmptyState
      icon={Compass}
      title="This page does not exist"
      description="The link may be out of date. Use the sidebar or Ctrl+K to find what you need."
      action={
        <Link to="/" className={buttonVariants()}>
          Go to the dashboard
        </Link>
      }
    />
  );
}
