import { History } from "lucide-react";
import { PageHeader } from "@/components/common";
import { EmptyState } from "@/components/states";

export default function RunsPage() {
  return (
    <>
      <PageHeader title="Runs" description="Start the agent and review past runs." />
      <EmptyState icon={History} title="Coming in a later phase" description="This screen is part of the implementation plan." />
    </>
  );
}
