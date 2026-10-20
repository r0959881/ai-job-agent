import * as React from "react";
import { Outlet, RouterProvider, createBrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import { ConfirmProvider } from "@/components/confirm";
import { AppShell } from "@/components/layout/AppShell";
import { RunDialogProvider } from "@/components/layout/RunControl";
import { RunNotifier } from "@/features/runs/RunNotifier";
import { SkeletonRows } from "@/components/states";
import { TooltipProvider } from "@/components/ui/overlays";
import { RequireUser } from "@/lib/session";
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
const LoginPage = React.lazy(() => import("@/pages/LoginPage"));

function ThemedToaster() {
  const { resolved } = useTheme();
  return <Toaster theme={resolved} position="bottom-right" richColors closeButton duration={5000} />;
}

/** Providers that need the router (navigation from dialogs) live inside it. Everything here needs a user. */
function RootLayout() {
  return (
    <RequireUser>
      <RunDialogProvider>
        <RunNotifier />
        <React.Suspense fallback={<SkeletonRows className="p-8" />}>
          <Outlet />
        </React.Suspense>
      </RunDialogProvider>
    </RequireUser>
  );
}

const page = (Component: React.ComponentType) => (
  <React.Suspense fallback={<SkeletonRows rows={8} />}>
    <Component />
  </React.Suspense>
);

export const routes = [
  { path: "/login", element: page(LoginPage) },
  {
    element: <RootLayout />,
    children: [
      { path: "/onboarding", element: page(OnboardingPage) },
      {
        element: <AppShell />,
        children: [
          { index: true, element: page(DashboardPage) },
          { path: "profile", element: page(ProfilePage) },
          { path: "jobs", element: page(JobsPage) },
          { path: "jobs/:id", element: page(JobDetailPage) },
          { path: "documents", element: page(DocumentsPage) },
          { path: "runs", element: page(RunsPage) },
          { path: "runs/:id", element: page(RunDetailPage) },
          { path: "settings", element: page(SettingsPage) },
          { path: "settings/:tab", element: page(SettingsPage) },
          { path: "*", element: page(NotFoundPage) },
        ],
      },
    ],
  },
];

const router = createBrowserRouter(routes);

export function App() {
  return (
    <ThemeProvider>
      <TooltipProvider delayDuration={300}>
        <ConfirmProvider>
          <RouterProvider router={router} />
          <ThemedToaster />
        </ConfirmProvider>
      </TooltipProvider>
    </ThemeProvider>
  );
}
