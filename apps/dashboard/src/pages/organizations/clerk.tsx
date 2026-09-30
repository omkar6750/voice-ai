import { CreateOrganization, OrganizationList, OrganizationProfile } from "@clerk/react";
import { clerkUrls } from "@/app/clerk-config";

const appearance = {
  variables: {
    colorPrimary: "#315efb",
    colorText: "#17223b",
    colorBackground: "#f8fafc",
    borderRadius: "0.75rem",
  },
};

export function OrganizationListPage() {
  return <main className="mx-auto flex min-h-svh max-w-3xl items-center justify-center p-6"><OrganizationList hidePersonal afterSelectOrganizationUrl={clerkUrls.afterSignIn} afterCreateOrganizationUrl={clerkUrls.organizationProfile} appearance={appearance} /></main>;
}

export function OrganizationCreatePage() {
  return <main className="mx-auto flex min-h-svh max-w-xl items-center justify-center p-6"><CreateOrganization afterCreateOrganizationUrl={clerkUrls.organizationProfile} appearance={appearance} /></main>;
}

export function OrganizationProfilePage() {
  return <main className="mx-auto max-w-5xl p-6"><OrganizationProfile routing="path" path={clerkUrls.organizationProfile} appearance={appearance} /></main>;
}
