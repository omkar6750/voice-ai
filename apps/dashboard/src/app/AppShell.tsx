import {
  Activity, AudioLines, CalendarClock, Database, Link2, ListTodo,
  LogOut, Radio, Settings2, Users,
} from "lucide-react";
import { UserButton, useClerk } from "@clerk/react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { AppRoutes } from "./AppRoutes";
import { QuickDial } from "./QuickDial";
import { TestAgentModal } from "./TestAgentModal";
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

function SideNavigation() {
  const { signOut } = useClerk();
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
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navigation.map(({ title, path, icon: Icon }) => (
                <SidebarMenuItem key={path}>
                  <SidebarMenuButton asChild tooltip={title} isActive={pathname === path || pathname.startsWith(`${path}/`)}>
                    <NavLink to={path}><Icon aria-hidden="true" /><span>{title}</span></NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
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
            <BreadcrumbLink asChild><Link to={parent?.path ?? "/runs"}>{parent?.title ?? "Workspace"}</Link></BreadcrumbLink>
          ) : <BreadcrumbPage>{parent?.title ?? "Workspace"}</BreadcrumbPage>}
        </BreadcrumbItem>
        {parts.length > 1 && <>
          <BreadcrumbSeparator />
          <BreadcrumbItem><BreadcrumbPage className="max-w-44 truncate">{parts[parts.length - 1].slice(0, 12)}</BreadcrumbPage></BreadcrumbItem>
        </>}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

export function AppShell() {
  return (
    <SidebarProvider>
      <SideNavigation />
      <SidebarInset className="min-w-0">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b px-4">
          <SidebarTrigger />
          <LocationTrail />
          <div className="ml-auto flex items-center gap-2">
            <TestAgentModal />
            <QuickDial />
            <UserButton />
          </div>
        </header>
        <main className="min-w-0 flex-1"><AppRoutes /></main>
      </SidebarInset>
    </SidebarProvider>
  );
}
