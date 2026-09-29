import { createContext, useContext, type ReactNode } from "react";

export type OrganizationAccess = {
  role: "org:admin" | "org:member" | null;
  isOwner: boolean;
  canManage: boolean;
  canUseBrowserTest: boolean;
  canDial: boolean;
};

export const OrganizationAccessContext = createContext<OrganizationAccess>({
  role: null,
  isOwner: false,
  canManage: false,
  canUseBrowserTest: false,
  canDial: false,
});

export function useOrganizationAccess(): OrganizationAccess {
  return useContext(OrganizationAccessContext);
}

export function AdminOnly({ children }: { children: ReactNode }) {
  return useOrganizationAccess().canManage ? children : null;
}
