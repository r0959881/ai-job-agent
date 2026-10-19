import { Settings } from "lucide-react";
import { PageHeader } from "@/components/common";
import { EmptyState } from "@/components/states";

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Search settings, integrations and data." />
      <EmptyState icon={Settings} title="Coming in a later phase" description="This screen is part of the implementation plan." />
    </>
  );
}
