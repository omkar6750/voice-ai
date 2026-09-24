import { Badge } from "@/components/ui/badge";

export function StatusBadge({ status }: { status: string }) {
  const variant =
    status === "failed" || status === "uncertain"
      ? "destructive"
      : status === "completed"
        ? "default"
        : "secondary";
  return (
    <Badge variant={variant} className="capitalize">
      {status.replaceAll("_", " ")}
    </Badge>
  );
}
