import { SignIn, SignUp } from "@clerk/react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { clerkUrls } from "@/app/clerk-config";
import { Brand, landingTheme } from "./LandingPage";
import { cn } from "@/lib/utils";

const appearance = {
  variables: {
    colorPrimary: "#52a8ff",
    colorBackground: "#0a0a0a",
    colorForeground: "#ededed",
    colorMutedForeground: "#999999",
    colorInputBackground: "#1f1f1f",
    colorInputForeground: "#ededed",
    borderRadius: "0px",
  },
};

export default function AuthPage({ mode }: { mode: "sign-in" | "sign-up" }) {
  return (
    <main
      className={cn(
        landingTheme,
        "relative isolate flex min-h-svh flex-col overflow-hidden",
      )}
    >
      <div className="absolute inset-0 -z-10 bg-linear-to-r from-black via-black/70 to-transparent" />
      <header className="flex items-center justify-between gap-4 px-6 py-7 md:px-12">
        <Brand />
        <Link
          to="/"
          className="flex items-center gap-2 text-xs text-muted-foreground"
        >
          <ArrowLeft className="size-4" />
          Back to platform
        </Link>
      </header>
      <div className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-12 px-6 py-12 md:grid-cols-2">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-primary">
            Your next conversation starts here
          </p>
          <h1 className="mt-6 text-5xl font-medium leading-tight tracking-[-.05em]">
            Build something
            <br />
            worth talking to.
          </h1>
          <p className="mt-5 max-w-sm text-sm leading-7 text-muted-foreground">
            Configure agents, test conversations and inspect the evidence. Your
            team's workspace is one step away.
          </p>
        </div>
        <div className="flex justify-center">
          {mode === "sign-in" ? (
            <SignIn
              appearance={appearance}
              routing="path"
              path={clerkUrls.signIn}
              signUpUrl={clerkUrls.signUp}
              forceRedirectUrl={clerkUrls.afterSignIn}
            />
          ) : (
            <SignUp
              appearance={appearance}
              routing="path"
              path={clerkUrls.signUp}
              signInUrl={clerkUrls.signIn}
              forceRedirectUrl={clerkUrls.afterSignUp}
            />
          )}
        </div>
      </div>
    </main>
  );
}
