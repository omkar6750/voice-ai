import type { ReactNode } from "react";
import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4 border-b pb-5">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action}
    </header>
  );
}

export function PageBody({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 lg:p-6">
      {children}
    </div>
  );
}

export function LoadState({
  loading,
  error,
  empty,
  children,
}: {
  loading: boolean;
  error: string | null;
  empty?: string;
  children: ReactNode;
}) {
  if (loading)
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  if (error)
    return (
      <Alert variant="destructive">
        <AlertCircle />
        <AlertTitle>Could not load</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  if (empty)
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>Nothing here yet</EmptyTitle>
          <EmptyDescription>{empty}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  return <>{children}</>;
}

export function StatusBadge({ value }: { value: string }) {
  return (
    <Badge
      variant={
        value === "failed" || value === "error"
          ? "destructive"
          : value === "published" || value === "completed"
            ? "default"
            : "secondary"
      }
    >
      {value.replaceAll("_", " ")}
    </Badge>
  );
}

export function ReadOnlyValue({
  label,
  value,
  reason,
}: {
  label: string;
  value: ReactNode;
  reason?: string;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value ?? "Not set"}</span>
      {reason && (
        <p className="w-full text-xs text-muted-foreground">{reason}</p>
      )}
    </div>
  );
}
