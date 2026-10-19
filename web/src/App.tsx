import * as React from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { ConfirmProvider } from "@/components/confirm";
import { AppShell } from "@/components/layout/AppShell";
import { RunDialogProvider } from "@/components/layout/RunControl";
import { SkeletonRows } from "@/components/states";
import { TooltipProvider } from "@/components/ui/overlays";
import { ThemeProvider, useTheme } from "@/lib/theme";

const DashboardPage = React.lazy(() => import("@/pages/DashboardPage"));
const ProfilePage = React.lazy(() => import("@/pages/ProfilePage"));
const JobsPage = React.lazy(() => import("@/pages/JobsPage"));
const JobDetailPage = React.lazy(() => import("@/pages/JobDetailPage"));
const DocumentsPage = React.lazy(() => import("@/pages/DocumentsPage"));
const RunsPage = React.lazy(() => import("@/pages/RunsPage"));
const RunDetailPage = React.lazy(() => import("@/pages/RunDetailPage"));
const SettingsPage = React.lazy(() => import("@/pages/SettingsPage"));
const OnboardingPage = React.lazy(() => import("@/pages/OnboardingPage"));
const NotFoundPage = React.lazy(() => import("@/pages/NotFoundPage"));

function ThemedToaster() {
  const { resolved } = useTheme();
  return <Toaster theme={resolved} position="bottom-right" richColors closeButton duration={5000} />;
}

export function App() {
  return (
    <ThemeProvider>
      <TooltipProvider delayDuration={300}>
        <ConfirmProvider>
          <BrowserRouter>
            <RunDialogProvider>
              <React.Suspense fallback={<SkeletonRows className="p-8" />}>
                <Routes>
                  <Route path="/onboarding" element={<OnboardingPage />} />
                  <Route element={<AppShell />}>
                    <Route index element={<DashboardPage />} />
                    <Route path="profile" element={<ProfilePage />} />
                    <Route path="jobs" element={<JobsPage />} />
                    <Route path="jobs/:id" element={<JobDetailPage />} />
                    <Route path="documents" element={<DocumentsPage />} />
                    <Route path="runs" element={<RunsPage />} />
                    <Route path="runs/:id" element={<RunDetailPage />} />
                    <Route path="settings" element={<SettingsPage />} />
                    <Route path="settings/:tab" element={<SettingsPage />} />
                    <Route path="*" element={<NotFoundPage />} />
                  </Route>
                </Routes>
              </React.Suspense>
            </RunDialogProvider>
          </BrowserRouter>
          <ThemedToaster />
        </ConfirmProvider>
      </TooltipProvider>
    </ThemeProvider>
  );
}
