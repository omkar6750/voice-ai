import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useResource } from "@/lib/resources";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import type { AgentConfig, BookablePerson, CallbackRole } from "./types";
import { normalizeCallbackScheduling } from "./types";

type CalendarIntegration = { id: string; display_name: string; provider: string; status: string; timezone: string; calendar_id: string };
function keyFor(value: string, fallback: string) { const key = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, ""); return key || fallback; }
const emptyRole = (): CallbackRole => ({ key: "", label: "", description: "", enabled: true });
const emptyPerson = (): BookablePerson => ({ key: "", name: "", roles: [], calendar_integration_id: "", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC", enabled: true });

export function CallbackSchedulingPanel({ config, change, disabled }: { config: AgentConfig; change: (value: AgentConfig) => void; disabled: boolean }) {
  const scheduling = normalizeCallbackScheduling(config.callback_scheduling);
  const calendars = useResource<{ integrations: CalendarIntegration[] }>("/calendar-integrations");
  const connected = useMemo(() => (calendars.data?.integrations ?? []).filter((item) => item.status === "connected"), [calendars.data]);
  const byId = useMemo(() => new Map((calendars.data?.integrations ?? []).map((item) => [item.id, item])), [calendars.data]);
  const [sheet, setSheet] = useState<"role" | "person" | null>(null);
  const [roleDraft, setRoleDraft] = useState<CallbackRole>(emptyRole());
  const [personDraft, setPersonDraft] = useState<BookablePerson>(emptyPerson());
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const update = (next: Partial<typeof scheduling>) => change({ ...config, callback_scheduling: { ...scheduling, ...next } });
  function openRole(role?: CallbackRole) { setEditingKey(role?.key ?? null); setRoleDraft(role ? { ...role } : emptyRole()); setError(null); setSheet("role"); }
  function openPerson(person?: BookablePerson) { setEditingKey(person?.key ?? null); setPersonDraft(person ? { ...person, roles: [...person.roles] } : emptyPerson()); setError(null); setSheet("person"); }
  function saveRole() {
    const role = { ...roleDraft, key: (roleDraft.key || keyFor(roleDraft.label, "role")).trim(), label: roleDraft.label.trim(), description: roleDraft.description.trim() };
    if (!role.label || !role.description) return setError("Role label and description are required.");
    if (scheduling.roles.some((item) => item.key === role.key && item.key !== editingKey)) return setError("Role keys must be unique.");
    update({ roles: editingKey ? scheduling.roles.map((item) => item.key === editingKey ? role : item) : [...scheduling.roles, role] }); setSheet(null);
  }
  function savePerson() {
    const person = { ...personDraft, key: (personDraft.key || keyFor(personDraft.name, "person")).trim(), name: personDraft.name.trim(), timezone: personDraft.timezone.trim() };
    if (!person.name || !person.key || !person.timezone) return setError("Name, key, and timezone are required.");
    if (!person.roles.length) return setError("Select at least one role.");
    if (!person.calendar_integration_id) return setError("Select a connected calendar.");
    if (scheduling.bookable_people.some((item) => item.key === person.key && item.key !== editingKey)) return setError("Person keys must be unique.");
    update({ bookable_people: editingKey ? scheduling.bookable_people.map((item) => item.key === editingKey ? person : item) : [...scheduling.bookable_people, person] }); setSheet(null);
  }
  function removeRole(key: string) { update({ roles: scheduling.roles.filter((role) => role.key !== key), bookable_people: scheduling.bookable_people.map((person) => ({ ...person, roles: person.roles.filter((role) => role !== key) })) }); }
  function removePerson(key: string) { update({ bookable_people: scheduling.bookable_people.filter((person) => person.key !== key) }); }
  const missingCalendars = scheduling.bookable_people.filter((person) => { const item = byId.get(person.calendar_integration_id); return !item || item.status !== "connected"; });
  return (
    <section className="flex max-w-4xl flex-col gap-6">
      <div><h2 className="text-base font-semibold">Human callback scheduling</h2><p className="text-sm text-muted-foreground">Route callback requests to named people and connected Google Calendars. Agent config stores only the integration ID.</p></div>
      <FieldGroup><Field><FieldLabel htmlFor="callback-enabled">Enable callback scheduling</FieldLabel><Input id="callback-enabled" type="checkbox" className="size-4" checked={scheduling.enabled} disabled={disabled} onChange={(event) => update({ enabled: event.target.checked })} /></Field><Field><FieldLabel>Callback duration</FieldLabel><FieldDescription>All callbacks are 15 minutes.</FieldDescription></Field><Field><FieldLabel htmlFor="callback-notice">Minimum notice (minutes)</FieldLabel><Input id="callback-notice" type="number" min={0} max={10080} value={scheduling.minimum_notice_minutes} disabled={disabled} onChange={(event) => update({ minimum_notice_minutes: Math.max(0, Number(event.target.value)) })} /></Field></FieldGroup>
      {missingCalendars.length > 0 && <Alert variant="destructive"><AlertTitle>Calendar disconnected</AlertTitle><AlertDescription>{missingCalendars.map((person) => person.name).join(", ")} has a missing or disconnected calendar. Reconnect it from <Link to="/integrations">Integrations</Link>; the reference is preserved.</AlertDescription></Alert>}
      <div className="flex items-center justify-between"><div><h3 className="font-medium">Callback roles</h3><p className="text-sm text-muted-foreground">Stable keys are generated once and are not changed when editing.</p></div><Button type="button" variant="outline" disabled={disabled} onClick={() => openRole()}><Plus className="size-4" />Add role</Button></div>
      <div className="grid gap-3 sm:grid-cols-2">{scheduling.roles.map((role) => <Card key={role.key}><CardHeader><CardTitle className="flex items-center justify-between gap-2"><span>{role.label}</span><span className="text-xs text-muted-foreground">{role.enabled ? "Enabled" : "Disabled"}</span></CardTitle><CardDescription>{role.description}</CardDescription></CardHeader><CardContent className="flex justify-end gap-2"><Button type="button" size="sm" variant="ghost" disabled={disabled} onClick={() => openRole(role)}><Pencil className="size-4" />Edit</Button><Button type="button" size="sm" variant="ghost" disabled={disabled} onClick={() => removeRole(role.key)}><Trash2 className="size-4" />Remove</Button></CardContent></Card>)}</div>
      {scheduling.roles.length === 0 && <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">No roles configured yet.</p>}
      <div className="flex items-center justify-between"><div><h3 className="font-medium">Bookable people</h3><p className="text-sm text-muted-foreground">Each person must use a connected calendar and at least one role.</p></div><Button type="button" variant="outline" disabled={disabled} onClick={() => openPerson()}><Plus className="size-4" />Add person</Button></div>
      <div className="grid gap-3 sm:grid-cols-2">{scheduling.bookable_people.map((person) => { const calendar = byId.get(person.calendar_integration_id); return <Card key={person.key}><CardHeader><CardTitle className="flex items-center justify-between gap-2"><span>{person.name}</span><span className="text-xs text-muted-foreground">{person.enabled ? "Enabled" : "Disabled"}</span></CardTitle><CardDescription>{person.roles.join(", ")} - {calendar?.display_name ?? "Calendar unavailable"} - {person.timezone}</CardDescription></CardHeader><CardContent className="flex justify-end gap-2"><Button type="button" size="sm" variant="ghost" disabled={disabled} onClick={() => openPerson(person)}><Pencil className="size-4" />Edit</Button><Button type="button" size="sm" variant="ghost" disabled={disabled} onClick={() => removePerson(person.key)}><Trash2 className="size-4" />Remove</Button></CardContent></Card> })}</div>
      {scheduling.bookable_people.length === 0 && <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">No bookable people configured yet.</p>}
      <Collapsible><CollapsibleTrigger asChild><Button type="button" variant="ghost">View generated configuration</Button></CollapsibleTrigger><CollapsibleContent><Textarea readOnly rows={12} value={JSON.stringify(scheduling, null, 2)} /></CollapsibleContent></Collapsible>
      <Sheet open={sheet !== null} onOpenChange={(open) => { if (!open) setSheet(null); }}><SheetContent><SheetHeader><SheetTitle>{sheet === "role" ? (editingKey ? "Edit role" : "Add role") : (editingKey ? "Edit person" : "Add person")}</SheetTitle><SheetDescription>Changes are saved with the agent draft.</SheetDescription></SheetHeader>
        {sheet === "role" ? <FieldGroup><Field><FieldLabel htmlFor="role-label">Label</FieldLabel><Input id="role-label" value={roleDraft.label} onChange={(event) => setRoleDraft({ ...roleDraft, label: event.target.value, key: editingKey ? roleDraft.key : keyFor(event.target.value, "role") })} /></Field><Field><FieldLabel htmlFor="role-key">Stable key</FieldLabel><Input id="role-key" value={roleDraft.key} disabled={editingKey !== null} onChange={(event) => setRoleDraft({ ...roleDraft, key: event.target.value })} /><FieldDescription>Used by callback requests and cannot change after creation.</FieldDescription></Field><Field><FieldLabel htmlFor="role-description">Description</FieldLabel><Textarea id="role-description" value={roleDraft.description} onChange={(event) => setRoleDraft({ ...roleDraft, description: event.target.value })} /></Field><Field><FieldLabel htmlFor="role-enabled">Enabled</FieldLabel><Input id="role-enabled" type="checkbox" className="size-4" checked={roleDraft.enabled} onChange={(event) => setRoleDraft({ ...roleDraft, enabled: event.target.checked })} /></Field></FieldGroup> : <FieldGroup><Field><FieldLabel htmlFor="person-name">Name</FieldLabel><Input id="person-name" value={personDraft.name} onChange={(event) => setPersonDraft({ ...personDraft, name: event.target.value, key: editingKey ? personDraft.key : keyFor(event.target.value, "person") })} /></Field><Field><FieldLabel htmlFor="person-key">Stable key</FieldLabel><Input id="person-key" value={personDraft.key} disabled={editingKey !== null} onChange={(event) => setPersonDraft({ ...personDraft, key: event.target.value })} /></Field><Field><FieldLabel>Roles</FieldLabel><div className="grid gap-2">{scheduling.roles.map((role) => <label key={role.key} className="flex items-center gap-2 text-sm"><Input type="checkbox" className="size-4" checked={personDraft.roles.includes(role.key)} onChange={(event) => setPersonDraft({ ...personDraft, roles: event.target.checked ? [...personDraft.roles, role.key] : personDraft.roles.filter((key) => key !== role.key) })} />{role.label}</label>)}</div></Field><Field><FieldLabel htmlFor="person-calendar">Calendar</FieldLabel><NativeSelect id="person-calendar" value={personDraft.calendar_integration_id} onChange={(event) => setPersonDraft({ ...personDraft, calendar_integration_id: event.target.value })}><NativeSelectOption value="">Select a connected calendar</NativeSelectOption>{connected.map((calendar) => <NativeSelectOption key={calendar.id} value={calendar.id}>{calendar.display_name}</NativeSelectOption>)}{personDraft.calendar_integration_id && !connected.some((calendar) => calendar.id === personDraft.calendar_integration_id) && <NativeSelectOption value={personDraft.calendar_integration_id}>Calendar disconnected</NativeSelectOption>}</NativeSelect><FieldDescription><Link to="/integrations">Manage calendar connections</Link></FieldDescription></Field><Field><FieldLabel htmlFor="person-timezone">Timezone</FieldLabel><Input id="person-timezone" value={personDraft.timezone} onChange={(event) => setPersonDraft({ ...personDraft, timezone: event.target.value })} /></Field><Field><FieldLabel htmlFor="person-enabled">Enabled</FieldLabel><Input id="person-enabled" type="checkbox" className="size-4" checked={personDraft.enabled} onChange={(event) => setPersonDraft({ ...personDraft, enabled: event.target.checked })} /></Field></FieldGroup>}
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}<SheetFooter><Button type="button" variant="outline" onClick={() => setSheet(null)}>Cancel</Button><Button type="button" onClick={sheet === "role" ? saveRole : savePerson}>Save</Button></SheetFooter>
      </SheetContent></Sheet>
    </section>
  );
}
