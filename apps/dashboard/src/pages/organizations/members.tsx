import { useState } from "react";
import { useAuth } from "@clerk/react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { useOrganizationAccess } from "@/app/access";
import { useApi } from "@/app/api";
import type { InvitationView, MemberView, OrganizationView } from "@/app/organizations";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Separator } from "@/components/ui/separator";
import { useResource } from "@/lib/resources";

export function OrganizationMembersPage({ organization }: { organization?: OrganizationView }) {
  const { orgId } = useParams();
  const api = useApi();
  const { userId } = useAuth();
  const { canManage } = useOrganizationAccess();
  const admin = organization?.role === "org:admin" || canManage;
  const { data: memberData, loading: membersLoading, error: membersError, reload: reloadMembers } = useResource<MemberView[]>(
    orgId ? `/orgs/${orgId}/members` : "",
    Boolean(orgId),
  );
  const { data: invitationData, loading: invitationsLoading, error: invitationsError, reload: reloadInvitations } = useResource<InvitationView[]>(
    orgId ? `/orgs/${orgId}/invitations` : "",
    Boolean(orgId) && admin,
  );
  const members = memberData ?? [];
  const invitations = invitationData ?? [];
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("org:member");
  const [nextOwner, setNextOwner] = useState("");
  const [pending, setPending] = useState(false);
  const error = membersError ?? invitationsError;
  const loading = membersLoading || invitationsLoading;
  const reload = async () => {
    await Promise.all([reloadMembers(), admin ? reloadInvitations() : Promise.resolve()]);
  };

  async function invite() {
    if (!orgId || !email.trim()) return;
    setPending(true);
    try {
      await api(`/orgs/${orgId}/invitations`, { method: "POST", body: JSON.stringify({ email_address: email.trim(), role }) });
      setEmail("");
      toast.success("Clerk invitation sent");
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Invitation failed");
    } finally {
      setPending(false);
    }
  }

  async function revoke(id: string) {
    if (!orgId) return;
    try {
      await api(`/orgs/${orgId}/invitations/${id}`, { method: "DELETE" });
      toast.success("Invitation revoked");
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not revoke invitation");
    }
  }

  async function changeRole(id: string, nextRole: string) {
    if (!orgId) return;
    try {
      await api(`/orgs/${orgId}/members/${id}`, { method: "PATCH", body: JSON.stringify({ role: nextRole }) });
      toast.success("Member role updated");
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not update member role");
    }
  }

  async function removeMember(id: string) {
    if (!orgId || !window.confirm("Remove this member from the organization?")) return;
    try {
      await api(`/orgs/${orgId}/members/${id}`, { method: "DELETE" });
      toast.success("Member removed");
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not remove member");
    }
  }

  async function transferOwnership() {
    if (!orgId || !nextOwner || !window.confirm("Transfer organization ownership to this member? You will remain an admin, but only the new owner can transfer it again.")) return;
    setPending(true);
    try {
      await api(`/orgs/${orgId}/ownership-transfer`, { method: "POST", body: JSON.stringify({ user_id: nextOwner }) });
      setNextOwner("");
      toast.success("Ownership transferred");
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not transfer ownership");
    } finally {
      setPending(false);
    }
  }

  const isOwner = organization?.is_owner ?? members.some((member) => member.is_owner);
  return <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
    <div>
      <h1 className="text-2xl font-semibold">{organization?.name ?? "Organization"} members</h1>
      <p className="text-sm text-muted-foreground">Clerk manages invitations and membership. Access begins only after acceptance.</p>
    </div>
    {error && <p role="alert" className="text-destructive">{error}</p>}
    <Card>
      <CardHeader><CardTitle>Members</CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-3">
        {members.map((member, index) => <div key={member.user_id} className="flex flex-col gap-3">
          {index > 0 && <Separator />}
          <div className="flex items-center justify-between gap-3">
            <span>{[member.first_name, member.last_name].filter(Boolean).join(" ") || member.email || member.user_id}</span>
            {admin && !member.is_owner && member.user_id !== userId ? <div className="flex items-center gap-2">
              <NativeSelect aria-label={`Role for ${member.email ?? member.user_id}`} value={member.role} onChange={(event) => void changeRole(member.user_id, event.target.value)}>
                <option value="org:member">Member</option><option value="org:admin">Admin</option>
              </NativeSelect>
              <Button size="sm" variant="outline" onClick={() => void removeMember(member.user_id)}>Remove</Button>
            </div> : <Badge variant="secondary">{member.is_owner ? "Owner" : member.role === "org:admin" ? "Admin" : "Member"}</Badge>}
          </div>
        </div>)}
        {loading && <p role="status" className="text-sm text-muted-foreground">Loading members…</p>}
        {!loading && members.length === 0 && !error && <p className="text-sm text-muted-foreground">No members found.</p>}
      </CardContent>
    </Card>
    {admin && <>
      <Card>
        <CardHeader><CardTitle>Invite a teammate</CardTitle><CardDescription>Clerk emails the invitation. The invitee signs up or signs in with that address.</CardDescription></CardHeader>
        <CardContent><FieldGroup>
          <Field><FieldLabel htmlFor="invite-email">Email address</FieldLabel><Input id="invite-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" /></Field>
          <Field><FieldLabel htmlFor="invite-role">Role</FieldLabel><NativeSelect id="invite-role" value={role} onChange={(event) => setRole(event.target.value)}><option value="org:member">Member</option><option value="org:admin">Admin</option></NativeSelect></Field>
          <Button disabled={pending || !email.trim()} onClick={() => void invite()}>{pending ? "Sending…" : "Send invitation"}</Button>
        </FieldGroup></CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Invitations</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-3">
          {invitations.map((invitation) => <div key={invitation.id} className="flex items-center justify-between gap-3">
            <span>{invitation.email_address} · {invitation.status} · {invitation.role === "org:admin" ? "Admin" : "Member"}</span>
            {invitation.status === "pending" && <Button size="sm" variant="outline" onClick={() => void revoke(invitation.id)}>Revoke</Button>}
          </div>)}
          {invitations.length === 0 && <p className="text-sm text-muted-foreground">No invitations yet.</p>}
        </CardContent>
      </Card>
    </>}
    {isOwner && <Card>
      <CardHeader><CardTitle>Transfer ownership</CardTitle><CardDescription>Choose an existing member. They will become an admin and the organization owner. You will remain an admin.</CardDescription></CardHeader>
      <CardContent><FieldGroup>
        <Field><FieldLabel htmlFor="next-owner">New owner</FieldLabel><NativeSelect id="next-owner" value={nextOwner} onChange={(event) => setNextOwner(event.target.value)}>
          <option value="">Select a member</option>
          {members.filter((member) => !member.is_owner && member.user_id !== userId).map((member) => <option key={member.user_id} value={member.user_id}>{[member.first_name, member.last_name].filter(Boolean).join(" ") || member.email || member.user_id}</option>)}
        </NativeSelect></Field>
        <Button variant="outline" disabled={!nextOwner || pending} onClick={() => void transferOwnership()}>Transfer ownership</Button>
      </FieldGroup></CardContent>
    </Card>}
  </div>;
}
