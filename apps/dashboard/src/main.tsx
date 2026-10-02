import { ClerkProvider } from "@clerk/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { App } from "./app/App";
import { clerkUrls } from "./app/clerk-config";
import { queryClient } from "./lib/query-client";
import "./styles.css";

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
if (!publishableKey) throw new Error("Clerk publishable key is not configured");

// Keep the existing nested routes; data-router support enables unsaved-edit guards.
const router = createBrowserRouter([{ path: "*", element: <App /> }]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ClerkProvider
        publishableKey={publishableKey}
        signInUrl={clerkUrls.signIn}
        signUpUrl={clerkUrls.signUp}
        afterSignOutUrl="/"
      >
        <RouterProvider router={router} />
      </ClerkProvider>
    </QueryClientProvider>
  </StrictMode>,
);
