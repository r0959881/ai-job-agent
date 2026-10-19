import { History } from "lucide-react";
import { PageHeader } from "@/components/common";
import { EmptyState } from "@/components/states";

export default function RunDetailPage() {
  return (
    <>
      <PageHeader title="Run" description="Live progress and logs." />
      <EmptyState icon={History} title="Coming in a later phase" description="This screen is part of the implementation plan." />
    </>
  );
}
