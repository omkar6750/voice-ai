import { Badge } from "@/components/ui/badge";

export function StatusBadge({
  status,
  outcome,
}: {
  status: string;
  outcome?: string | null;
}) {
  const variant =
    status === "failed" || status === "uncertain"
      ? "destructive"
      : status === "completed"
        ? "default"
        : "secondary";
  return (
    <Badge variant={variant} className="capitalize">
      {(status === "failed" &&
      ["busy", "no_answer", "call_rejected", "voicemail"].includes(
        outcome ?? "",
      )
        ? outcome!
        : status
      ).replaceAll("_", " ")}
    </Badge>
  );
}
