import { Badge } from "@/components/ui/badge";

export function callOutcomeLabel(outcome: string) {
  const labels: Record<string, string> = {
    busy: "Busy",
    no_answer: "No answer",
    call_rejected: "Call rejected",
    voicemail: "Voicemail",
    remote_hangup: "Other side ended",
    remote_hangup_likely: "Likely other side",
    local_hangup: "Ended locally",
    network_failure: "Network ended call",
    modem_failure: "Modem failure",
    dial_failed: "Dial failed",
    connection_timeout: "Connection timeout",
    provider_failure: "Provider failure",
    pipeline_failure: "Pipeline failure",
    evidence_failure: "Evidence could not be saved",
    execution_lease_expired: "Runtime lease expired",
    duration_limit: "Duration limit reached",
    disconnect_unknown: "Disconnect · unknown cause",
  };
  return labels[outcome] ?? outcome.replaceAll("_", " ");
}

export function StatusBadge({
  status,
  outcome,
}: {
  status: string;
  outcome?: string | null;
}) {
  const showOutcome =
    status !== "completed" && status !== "uncertain" && Boolean(outcome);
  const display = showOutcome
    ? callOutcomeLabel(outcome!)
    : status === "uncertain"
      ? "Needs recovery"
      : status.replaceAll("_", " ");
  const variant =
    showOutcome && outcome === "remote_hangup"
      ? "secondary"
      : status === "failed" || status === "uncertain"
        ? "destructive"
        : status === "completed"
          ? "default"
          : "secondary";
  return (
    <Badge variant={variant} className="capitalize">
      {display}
    </Badge>
  );
}
