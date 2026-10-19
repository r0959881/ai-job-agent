import { UserRound } from "lucide-react";
import { PageHeader } from "@/components/common";
import { EmptyState } from "@/components/states";

export default function ProfilePage() {
  return (
    <>
      <PageHeader title="Profile" description="Your master resume. Every tailored CV is built from it." />
      <EmptyState icon={UserRound} title="Coming in a later phase" description="This screen is part of the implementation plan." />
    </>
  );
}
