import { cloneElement, isValidElement, useId, type ReactNode } from "react";
import { Button as ShadcnButton } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NativeSelect } from "@/components/ui/native-select";
import { Field as ShadcnField, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";

export { Input, Textarea };

export function Button({
  variant = "primary",
  ...props
}: Omit<React.ComponentProps<typeof ShadcnButton>, "variant"> & {
  variant?: "primary" | "secondary" | "ghost";
}) {
  return <ShadcnButton variant={variant === "primary" ? "default" : variant === "secondary" ? "outline" : "ghost"} {...props} />;
}

export function Select(props: React.ComponentProps<typeof NativeSelect>) {
  return <NativeSelect className="w-full" {...props} />;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  const id = useId();
  const control = isValidElement(children)
    ? cloneElement(children as React.ReactElement<{ id?: string }>, { id })
    : children;
  return (
    <ShadcnField>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      {control}
      {hint && <FieldDescription>{hint}</FieldDescription>}
    </ShadcnField>
  );
}

export function Island({
  title, description, action, children,
}: { title: string; description?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
        {action && <CardAction>{action}</CardAction>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function Status({ value }: { value: string }) {
  const variant = value === "published" || value === "completed"
    ? "default" : value === "failed" || value === "uncertain"
      ? "destructive" : "secondary";
  return <Badge variant={variant} className="capitalize">{value.replaceAll("_", " ")}</Badge>;
}

export function Notice({ text, error = false }: { text: string; error?: boolean }) {
  return <Alert variant={error ? "destructive" : "default"} role={error ? "alert" : "status"}>
    <AlertDescription>{text}</AlertDescription>
  </Alert>;
}
