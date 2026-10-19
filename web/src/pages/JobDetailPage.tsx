import { Briefcase } from "lucide-react";
import { PageHeader } from "@/components/common";
import { EmptyState } from "@/components/states";

export default function JobDetailPage() {
  return (
    <>
      <PageHeader title="Job" description="Everything you need to apply." />
      <EmptyState icon={Briefcase} title="Coming in a later phase" description="This screen is part of the implementation plan." />
    </>
  );
}
