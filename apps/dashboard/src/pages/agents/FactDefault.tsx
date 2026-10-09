import { useState } from "react";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import type { AgentConfig } from "./types";
type Slot = AgentConfig["fact_slots"][number];
export function FactDefault({
  slot,
  disabled,
  change,
}: {
  slot: Slot;
  disabled: boolean;
  change: (value: Slot["default_value"]) => void;
}) {
  const value = slot.default_value ?? "";
  const [unset, setUnset] = useState(value === "");
  const invalid =
    !unset &&
    value !== "" &&
    ((slot.value_type === "string" && typeof value !== "string") ||
      (slot.value_type === "boolean" && typeof value !== "boolean") ||
      (["integer", "number"].includes(slot.value_type) &&
        (typeof value !== "number" || !Number.isFinite(value))) ||
      (slot.value_type === "integer" && !Number.isInteger(value)) ||
      (typeof value === "number" &&
        ((slot.minimum !== null && value < slot.minimum) ||
          (slot.maximum !== null && value > slot.maximum))) ||
      (Array.isArray(slot.enum) && !slot.enum.includes(value)));
  return (
    <Field data-invalid={invalid || undefined}>
      <FieldLabel>Default value</FieldLabel>
      <NativeSelect
        aria-label={`Default mode for ${slot.key}`}
        value={unset ? "unset" : "value"}
        disabled={disabled}
        onChange={(e) => {
          setUnset(e.target.value === "unset");
          change(
            e.target.value === "unset"
              ? ""
              : slot.value_type === "boolean"
                ? false
                : slot.value_type === "string"
                  ? ""
                  : 0,
          );
        }}
      >
        <option value="unset">Unset (empty string)</option>
        <option value="value">Value</option>
      </NativeSelect>
      {!unset &&
        (slot.value_type === "boolean" ? (
          <NativeSelect
            aria-label={`Default for ${slot.key}`}
            disabled={disabled}
            value={String(value)}
            onChange={(e) => change(e.target.value === "true")}
          >
            <option value="false">false</option>
            <option value="true">true</option>
          </NativeSelect>
        ) : (
          <Input
            aria-label={`Default for ${slot.key}`}
            aria-invalid={invalid}
            disabled={disabled}
            type={slot.value_type === "string" ? "text" : "number"}
            value={String(value)}
            step={slot.value_type === "integer" ? 1 : "any"}
            onChange={(e) =>
              change(
                e.target.value === ""
                  ? ""
                  : slot.value_type === "string"
                    ? e.target.value
                    : Number(e.target.value),
              )
            }
          />
        ))}
      <FieldDescription>
        {invalid
          ? "Default must match the fact type, enum and range."
          : "Initial value for each new conversation. Unset stays empty until recorded."}
      </FieldDescription>
    </Field>
  );
}
