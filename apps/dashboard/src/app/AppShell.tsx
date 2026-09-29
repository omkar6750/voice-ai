import {
  Activity, AudioLines, CalendarClock, Database, Link2, ListTodo,
  LogOut, Radio, Settings2, ShieldCheck, Users,
} from "lucide-react";
import { UserButton, useAuth, useClerk } from "@clerk/react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { AppRoutes } from "./AppRoutes";
import { QuickDial } from "./QuickDial";
import { TestAgentModal } from "./TestAgentModal";
import { OrgSwitcher } from "./OrgSwitcher";
import { OrganizationAccessContext, type OrganizationAccess } from "./access";
import type { OrganizationView } from "./organizations";
import {
  Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList,
  BreadcrumbPage, BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent,
  SidebarGroupLabel, SidebarHeader, SidebarInset, SidebarMenu,
  SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarTrigger,
} from "@/components/ui/sidebar";

const navigation = [
  { title: "Agents", path: "/agents", icon: AudioLines },
  { title: "Runs", path: "/runs", icon: Activity },
  { title: "Contacts", path: "/contacts", icon: Users },
  { title: "Knowledge", path: "/knowledge", icon: Database },
  { title: "Tools", path: "/tools", icon: ListTodo },
  { title: "Integrations", path: "/integrations", icon: Link2 },
  { title: "Callbacks", path: "/callbacks", icon: CalendarClock },
  { title: "Endpoints", path: "/endpoints", icon: Radio },
  { title: "Settings", path: "/settings", icon: Settings2 },
] as const;

function SideNavigation({ platformAdmin, canManageHardware, supportMode }: { platformAdmin: boolean; canManageHardware: boolean; supportMode: boolean }) {
  const { signOut } = useClerk();
  const { orgId } = useAuth();
  const { pathname } = useLocation();
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <Link to="/runs" className="flex min-h-10 items-center gap-2 px-2 text-sm font-semibold">
          <AudioLines aria-hidden="true" className="size-4" />
          <span className="group-data-[collapsible=icon]:hidden">Voice AI</span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Organization</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navigation.filter((item) => item.path !== "/endpoints" || canManageHardware).map(({ title, path, icon: Icon }) => (
                <SidebarMenuItem key={path}>
                  <SidebarMenuButton asChild tooltip={title} isActive={pathname === path || pathname.startsWith(`${path}/`)}>
                    <NavLink to={path}><Icon aria-hidden="true" /><span>{title}</span></NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
              {orgId && !supportMode && <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Members" isActive={pathname === `/orgs/${orgId}/members`}>
                  <NavLink to={`/orgs/${orgId}/members`}><Users aria-hidden="true" /><span>Members</span></NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>}
              {platformAdmin && <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Platform organizations" isActive={pathname === "/platform/orgs"}>
                  <NavLink to="/platform/orgs"><ShieldCheck aria-hidden="true" /><span>Platform organizations</span></NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={() => void signOut()} tooltip="Sign out">
              <LogOut aria-hidden="true" /><span>Sign out</span>
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
        <BreadcrumbItem><BreadcrumbLink asChild><Link to="/runs">Voice AI</Link></BreadcrumbLink></BreadcrumbItem>
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          {parts.length > 1 ? (
            <BreadcrumbLink asChild><Link to={parent?.path ?? "/runs"}>{parent?.title ?? "Organization"}</Link></BreadcrumbLink>
          ) : <BreadcrumbPage>{parent?.title ?? "Organization"}</BreadcrumbPage>}
        </BreadcrumbItem>
        {parts.length > 1 && <>
          <BreadcrumbSeparator />
          <BreadcrumbItem><BreadcrumbPage className="max-w-44 truncate">{parts[parts.length - 1].slice(0, 12)}</BreadcrumbPage></BreadcrumbItem>
        </>}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

export function AppShell({ organizations, platformAdmin = false, supportOrganization, onExitSupport }: { organizations: OrganizationView[]; platformAdmin?: boolean; supportOrganization?: { id: string; name: string }; onExitSupport?: () => void }) {
  const { orgId } = useAuth();
  const canCall = Boolean(supportOrganization) || organizations.some((org) => org.id === orgId);
  const activeOrganization = organizations.find((org) => org.id === orgId);
  const role: OrganizationAccess["role"] = supportOrganization || activeOrganization?.role === "org:admin"
    ? "org:admin"
    : activeOrganization?.role === "org:member"
      ? "org:member"
      : null;
  const access = {
    role,
    isOwner: Boolean(activeOrganization?.is_owner),
    canManage: Boolean(supportOrganization) || role === "org:admin",
    canUseBrowserTest: canCall,
    canDial: !supportOrganization && role === "org:admin",
  };
  const canDial = !supportOrganization && activeOrganization?.role === "org:admin";
  return (
    <OrganizationAccessContext.Provider value={access}>
    <SidebarProvider>
      <SideNavigation platformAdmin={platformAdmin} canManageHardware={canDial} supportMode={Boolean(supportOrganization)} />
      <SidebarInset className="min-w-0">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b px-4">
          <SidebarTrigger />
          <LocationTrail />
          {supportOrganization && <div className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs" role="status">
            <span>Support mode: {supportOrganization.name}</span>
            <button className="font-medium underline" onClick={onExitSupport}>Exit</button>
          </div>}
          <div className="ml-auto flex items-center gap-2">
            {!supportOrganization && <OrgSwitcher organizations={organizations} />}
            {canCall && <TestAgentModal />}
            {canDial && <QuickDial />}
            <UserButton />
          </div>
        </header>
        <main className="min-w-0 flex-1">
          {!access.canManage && <div className="border-b bg-muted/40 px-6 py-2 text-sm text-muted-foreground" role="status">Member access is read-only. You can review organization data and make browser test calls.</div>}
          <AppRoutes />
        </main>
      </SidebarInset>
    </SidebarProvider>
    </OrganizationAccessContext.Provider>
  );
}
