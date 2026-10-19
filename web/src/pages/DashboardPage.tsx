import { LayoutDashboard } from "lucide-react";
import { PageHeader } from "@/components/common";
import { EmptyState } from "@/components/states";

export default function DashboardPage() {
  return (
    <>
      <PageHeader title="Dashboard" description="Your job search at a glance." />
      <EmptyState icon={LayoutDashboard} title="Coming in a later phase" description="This screen is part of the implementation plan." />
    </>
  );
}
