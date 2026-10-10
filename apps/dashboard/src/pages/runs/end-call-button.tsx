import { useState } from "react";
import { PhoneOff } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { useOrganizationAccess } from "@/app/access";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { isActive } from "./model";
import type { components } from "@/generated/api";

export function EndCallButton({
  run,
  onRequested,
}: {
  run: { id: string; status: string; channel: string };
  onRequested: () => void;
}) {
  const api = useApi();
  const access = useOrganizationAccess();
  const [pending, setPending] = useState(false);
  if (
    !access.canManage ||
    !isActive(run.status) ||
    !["phone", "browser"].includes(run.channel)
  )
    return null;

  async function endCall() {
    setPending(true);
    try {
      const result = await api<components["schemas"]["StopRunResponse"]>(
        `/runs/${run.id}/stop`,
        { method: "POST" },
      );
      toast.success(
        result.status === "cancelled" || !result.stop_requested
          ? "Call has ended."
          : "End call requested. Waiting for runtime cleanup.",
      );
      onRequested();
    } catch (error) {
      setPending(false);
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not confirm the end request",
      );
      onRequested();
    }
  }

  return (
    <Button
      variant="destructive"
      size="sm"
      disabled={pending}
      onClick={() => void endCall()}
      aria-label={`End call ${run.id.slice(0, 8)}`}
    >
      {pending ? (
        <Spinner data-icon="inline-start" />
      ) : (
        <PhoneOff data-icon="inline-start" />
      )}
      {pending ? "Ending…" : "End call"}
    </Button>
  );
}
