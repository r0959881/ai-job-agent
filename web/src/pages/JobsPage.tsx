import { Briefcase } from "lucide-react";
import { PageHeader } from "@/components/common";
import { EmptyState } from "@/components/states";

export default function JobsPage() {
  return (
    <>
      <PageHeader title="Jobs" description="Every job the agent has found." />
      <EmptyState icon={Briefcase} title="Coming in a later phase" description="This screen is part of the implementation plan." />
    </>
  );
}
