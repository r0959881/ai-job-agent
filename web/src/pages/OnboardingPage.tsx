import { Sparkles } from "lucide-react";
import { PageHeader } from "@/components/common";
import { EmptyState } from "@/components/states";

export default function OnboardingPage() {
  return (
    <>
      <PageHeader title="Welcome" description="Set up your profile." />
      <EmptyState icon={Sparkles} title="Coming in a later phase" description="This screen is part of the implementation plan." />
    </>
  );
}
