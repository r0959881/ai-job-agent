import { FileText } from "lucide-react";
import { PageHeader } from "@/components/common";
import { EmptyState } from "@/components/states";

export default function DocumentsPage() {
  return (
    <>
      <PageHeader title="Documents" description="Tailored CVs, cover letters and reports." />
      <EmptyState icon={FileText} title="Coming in a later phase" description="This screen is part of the implementation plan." />
    </>
  );
}
