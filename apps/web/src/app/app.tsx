import { RouterProvider } from "react-router-dom";

import { AppErrorBoundary } from "@/app/error-boundary";
import { AppProviders } from "@/app/providers";
import { router } from "@/app/router";

export function App() {
  return (
    <AppProviders>
      <AppErrorBoundary>
        <RouterProvider router={router} />
      </AppErrorBoundary>
    </AppProviders>
  );
}
