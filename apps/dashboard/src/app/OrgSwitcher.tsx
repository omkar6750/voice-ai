import { useAuth, useClerk } from "@clerk/react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { NativeSelect } from "@/components/ui/native-select";
import type { OrganizationView } from "./organizations";

export function OrgSwitcher({ organizations }: { organizations: OrganizationView[] }) {
  const { orgId } = useAuth();
  const clerk = useClerk();
  const navigate = useNavigate();
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="sr-only">Organization</span>
      <NativeSelect
        aria-label="Organization"
        className="max-w-44"
        value={orgId ?? ""}
        onChange={(event) => {
          const id = event.target.value;
          if (!organizations.some((org) => org.id === id && org.registered)) return;
          void clerk.setActive({ organization: id })
            .then(() => navigate(organizations.some((org) => org.id === id && org.registered) ? `/orgs/${id}` : "/orgs"))
            .catch(() => toast.error("Could not switch organizations"));
        }}
      >
        <option value="" disabled>Select organization</option>
        {organizations.map((org) => <option key={org.id} value={org.id} disabled={!org.registered}>{org.name}{org.registered ? "" : " (setup pending)"}</option>)}
      </NativeSelect>
    </label>
  );
}
