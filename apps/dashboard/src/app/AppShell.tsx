import {
  Activity,
  AudioLines,
  CalendarClock,
  Database,
  Link2,
  ListTodo,
  LogOut,
  PhoneCall,
  Radio,
  Settings2,
  ShieldCheck,
  Users,
} from "lucide-react";
import {
  OrganizationSwitcher,
  UserButton,
  useAuth,
  useClerk,
} from "@clerk/react";
import { lazy, Suspense, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { AppRoutes } from "./AppRoutes";
import { useAppContext } from "./app-context";
import { clerkUrls } from "./clerk-config";
import { OrganizationAccessContext, type OrganizationAccess } from "./access";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";

const QuickDial = lazy(() =>
  import("./QuickDial").then((module) => ({ default: module.QuickDial })),
);
const TestAgentModal = lazy(() =>
  import("./TestAgentModal").then((module) => ({
    default: module.TestAgentModal,
  })),
);

function TestAgentLoadingDialog() {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 backdrop-blur-xs"
      role="status"
    >
      <div className="w-[calc(100%-2rem)] max-w-lg rounded-xl border border-border bg-card p-6 shadow-xl">
        <div className="flex flex-col gap-1.5">
          <p className="font-heading text-lg font-semibold">Test Agent</p>
          <p className="text-sm text-muted-foreground">
            Loading test call controls…
          </p>
        </div>
        <div className="mt-6 flex flex-col gap-4 animate-pulse">
          <div className="h-3 w-20 rounded bg-muted" />
          <div className="h-8 w-full rounded-lg bg-muted" />
          <div className="h-24 w-full rounded-lg bg-muted" />
        </div>
      </div>
    </div>
  );
}

function DeferredQuickDial() {
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        size="sm"
        onClick={() => {
          setLoaded(true);
          setOpen(true);
        }}
      >
        <PhoneCall data-icon="inline-start" />
        Quick dial
      </Button>
      {loaded && (
        <Suspense fallback={null}>
          <QuickDial open={open} onOpenChange={setOpen} hideTrigger />
        </Suspense>
      )}
    </>
  );
}

function DeferredTestAgentModal() {
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="gap-2"
        onClick={() => {
          setLoaded(true);
          setOpen(true);
        }}
      >
        <Radio className="size-4 text-emerald-500 animate-pulse" />
        <span>Test Agent</span>
      </Button>
      {loaded && (
        <Suspense fallback={open ? <TestAgentLoadingDialog /> : null}>
          <TestAgentModal open={open} onOpenChange={setOpen} hideTrigger />
        </Suspense>
      )}
    </>
  );
}

const navigation = [
  { title: "Agents", path: "/agents", icon: AudioLines },
  { title: "Runs", path: "/runs", icon: Activity },
  { title: "Recordings", path: "/recordings", icon: AudioLines },
  { title: "Contacts", path: "/contacts", icon: Users },
  { title: "Referrals", path: "/referrals", icon: Users },
  { title: "Knowledge", path: "/knowledge", icon: Database },
  { title: "Tools", path: "/tools", icon: ListTodo },
  { title: "Integrations", path: "/integrations", icon: Link2 },
  { title: "Callbacks", path: "/callbacks", icon: CalendarClock },
  { title: "Endpoints", path: "/endpoints", icon: Radio },
  { title: "Settings", path: "/settings", icon: Settings2 },
] as const;

function SideNavigation({
  platformAdmin,
  supportMode,
}: {
  platformAdmin: boolean;
  supportMode: boolean;
}) {
  const { signOut } = useClerk();
  const { orgId } = useAuth();
  const { pathname } = useLocation();
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <Link
          to="/runs"
          className="flex min-h-10 items-center gap-2 px-2 text-sm font-semibold"
        >
          <AudioLines aria-hidden="true" className="size-4" />
          <span className="group-data-[collapsible=icon]:hidden">Voice AI</span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Organization</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navigation
                .filter(
                  (item) =>
                    (item.path !== "/endpoints" || platformAdmin) &&
                    (item.path !== "/recordings" || !supportMode),
                )
                .map(({ title, path, icon: Icon }) => (
                  <SidebarMenuItem key={path}>
                    <SidebarMenuButton
                      asChild
                      tooltip={title}
                      isActive={
                        pathname === path || pathname.startsWith(`${path}/`)
                      }
                    >
                      <NavLink to={path}>
                        <Icon aria-hidden="true" />
                        <span>{title}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              {orgId && !supportMode && (
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    tooltip="Members"
                    isActive={pathname.startsWith("/organizations/profile")}
                  >
                    <NavLink to="/organizations/profile">
                      <Users aria-hidden="true" />
                      <span>Members</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              )}
              {platformAdmin && (
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    tooltip="Platform"
                    isActive={pathname === "/platform/orgs"}
                  >
                    <NavLink to="/platform/orgs">
                      <ShieldCheck aria-hidden="true" />
                      <span>Platform</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={() => void signOut()}
              tooltip="Sign out"
            >
              <LogOut aria-hidden="true" />
              <span>Sign out</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}

function LocationTrail() {
  const { pathname } = useLocation();
  const parts = pathname.split("/").filter(Boolean);
  const parent = navigation.find((item) => item.path === `/${parts[0]}`);
  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink asChild>
            <Link to="/runs">Voice AI</Link>
          </BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          {parts.length > 1 ? (
            <BreadcrumbLink asChild>
              <Link to={parent?.path ?? "/runs"}>
                {parent?.title ?? "Organization"}
              </Link>
            </BreadcrumbLink>
          ) : (
            <BreadcrumbPage>{parent?.title ?? "Organization"}</BreadcrumbPage>
          )}
        </BreadcrumbItem>
        {parts.length > 1 && (
          <>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage className="max-w-44 truncate">
                {parts[parts.length - 1].slice(0, 12)}
              </BreadcrumbPage>
            </BreadcrumbItem>
          </>
        )}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

export function AppShell({
  platformAdmin = false,
  supportOrganization,
  onExitSupport,
}: {
  platformAdmin?: boolean;
  supportOrganization?: { id: string; name: string };
  onExitSupport?: () => void;
}) {
  const { orgId } = useAuth();
  const appContext = useAppContext(Boolean(orgId));
  const capabilities = appContext.data?.capabilities ?? [];
  const canCall =
    Boolean(supportOrganization) || capabilities.includes("browser_test");
  const role: OrganizationAccess["role"] = supportOrganization
    ? "org:admin"
    : (appContext.data?.active_org_role ?? null);
  const canManage =
    Boolean(supportOrganization) || capabilities.includes("configure");
  const canDial = !supportOrganization && canManage;
  const access = {
    role,
    isOwner: !supportOrganization && appContext.data?.is_owner === true,
    canManage,
    canUseBrowserTest: canCall,
    canDial,
  };
  return (
    <OrganizationAccessContext.Provider value={access}>
      <SidebarProvider>
        <SideNavigation
          platformAdmin={platformAdmin}
          supportMode={Boolean(supportOrganization)}
        />
        <SidebarInset className="min-w-0">
          <header className="flex h-12 shrink-0 items-center gap-3 border-b px-4">
            <SidebarTrigger />
            <LocationTrail />
            {supportOrganization && (
              <div
                className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs"
                role="status"
              >
                <span>Support mode: {supportOrganization.name}</span>
                <button
                  className="font-medium underline"
                  onClick={onExitSupport}
                >
                  Exit
                </button>
              </div>
            )}
            <div className="ml-auto flex items-center gap-2">
              {!supportOrganization && (
                <OrganizationSwitcher
                  hidePersonal
                  afterSelectOrganizationUrl={clerkUrls.afterSignIn}
                  createOrganizationMode="navigation"
                  createOrganizationUrl={clerkUrls.createOrganization}
                  organizationProfileMode="navigation"
                  organizationProfileUrl={clerkUrls.organizationProfile}
                />
              )}
              {canCall && <DeferredTestAgentModal />}
              {canDial && <DeferredQuickDial />}
              <UserButton />
            </div>
          </header>
          <main className="min-w-0 flex-1">
            {!access.canManage && (
              <div
                className="border-b bg-muted/40 px-6 py-2 text-sm text-muted-foreground"
                role="status"
              >
                Member access is read-only. You can review organization data and
                make browser test calls.
              </div>
            )}
            <AppRoutes platformAdmin={platformAdmin} />
          </main>
        </SidebarInset>
      </SidebarProvider>
    </OrganizationAccessContext.Provider>
  );
}
