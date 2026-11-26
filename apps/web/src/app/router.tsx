import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "@/app/app-shell";
import { RouteErrorPage } from "@/app/route-error-page";
import { AuthCallbackPage, NotFoundPage, RequireAuth } from "@/app/routes";
import { ApprovalsPage } from "@/features/governance/ApprovalsPage";
import { AuditPage } from "@/features/governance/AuditPage";
import IntegrationPage from "@/features/admin/IntegrationPage";
import { AiInboxPage } from "@/features/ai-inbox/AiInboxPage";
import { AssistantPage } from "@/features/assistant/AssistantPage";
import { CapacityPage } from "@/features/capacity/CapacityPage";
import { ExecutivePage } from "@/features/executive/ExecutivePage";
import { PresenterPage } from "@/features/executive/PresenterPage";
import { GraphExplorerPage } from "@/features/graph/GraphExplorerPage";
import { ItemsPage } from "@/features/items/ItemsPage";
import { ItemDetailPage } from "@/features/items/ItemDetailPage";
import { RiskPage } from "@/features/risk/RiskPage";
import { PrioritizationPage } from "@/features/prioritization/PrioritizationPage";
import { LoginPage } from "@/features/auth/login-page";
import DashboardPage from "@/features/dashboard/DashboardPage";

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
    errorElement: <RouteErrorPage />,
  },
  {
    path: "/auth/callback",
    element: <AuthCallbackPage />,
    errorElement: <RouteErrorPage />,
  },
  {
    element: <RequireAuth />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          {
            path: "objectives",
            element: (
              <ItemsPage
                type="objective"
                titleKey="nav.objectives"
                createTitleKey="nav.objectives"
              />
            ),
          },
          {
            path: "demand",
            element: <ItemsPage type="demand" titleKey="nav.demand" createTitleKey="nav.demand" />,
          },
          {
            path: "portfolio",
            element: (
              <ItemsPage type="project" titleKey="nav.portfolio" createTitleKey="nav.portfolio" />
            ),
          },
          {
            path: "tasks",
            element: <ItemsPage type="task" titleKey="nav.tasks" createTitleKey="nav.tasks" />,
          },
          { path: "capacity", element: <CapacityPage /> },
          { path: "executive", element: <ExecutivePage /> },
          { path: "executive/presenter", element: <PresenterPage /> },
          { path: "risk", element: <RiskPage /> },
          { path: "assistant", element: <AssistantPage /> },
          { path: "prioritization", element: <PrioritizationPage /> },
          { path: "items/:id", element: <ItemDetailPage /> },
          { path: "graph", element: <GraphExplorerPage /> },
          { path: "ai/inbox", element: <AiInboxPage /> },
          { path: "admin/connectors", element: <IntegrationPage /> },
          { path: "approvals", element: <ApprovalsPage /> },
          { path: "audit", element: <AuditPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
