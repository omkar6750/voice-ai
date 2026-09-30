export const clerkUrls = {
  signIn: import.meta.env.VITE_CLERK_SIGN_IN_URL ?? "/sign-in",
  signUp: import.meta.env.VITE_CLERK_SIGN_UP_URL ?? "/sign-up",
  afterSignIn: import.meta.env.VITE_CLERK_AFTER_SIGN_IN_URL ?? "/runs",
  afterSignUp: import.meta.env.VITE_CLERK_AFTER_SIGN_UP_URL ?? "/organizations",
  organizationProfile: import.meta.env.VITE_CLERK_ORGANIZATION_PROFILE_URL ?? "/organizations/profile",
  createOrganization: import.meta.env.VITE_CLERK_CREATE_ORGANIZATION_URL ?? "/organizations/create",
  invitationRedirect: import.meta.env.VITE_CLERK_INVITATION_REDIRECT_URL ?? "/accept-invitation",
} as const;
