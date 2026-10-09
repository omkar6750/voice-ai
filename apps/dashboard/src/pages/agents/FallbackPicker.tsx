import { useState } from "react";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
export function FallbackPicker({
  variables,
  disabled,
  insert,
}: {
  variables: string[];
  disabled: boolean;
  insert: (text: string) => void;
}) {
  const [open, setOpen] = useState(false),
    [keys, setKeys] = useState<string[]>([]);
  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled || variables.length === 0}
        onClick={() => {
          setKeys([variables[0], variables[0]]);
          setOpen(true);
        }}
      >
        Insert fallback
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Fallback variables</DialogTitle>
            <DialogDescription>
              Later values override earlier values when nonempty. Empty strings,
              spaces and numeric zero fall back. Booleans are excluded.
            </DialogDescription>
          </DialogHeader>
          {keys.map((key, index) => (
            <Field key={index}>
              <FieldLabel>Priority {index + 1}</FieldLabel>
              <NativeSelect
                aria-label={`Fallback variable ${index + 1}`}
                value={key}
                onChange={(e) =>
                  setKeys(
                    keys.map((k, i) => (i === index ? e.target.value : k)),
                  )
                }
              >
                {variables.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={index === 0}
                  onClick={() => {
                    const next = [...keys];
                    [next[index - 1], next[index]] = [
                      next[index],
                      next[index - 1],
                    ];
                    setKeys(next);
                  }}
                >
                  Move earlier
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={index === keys.length - 1}
                  onClick={() => {
                    const next = [...keys];
                    [next[index + 1], next[index]] = [
                      next[index],
                      next[index + 1],
                    ];
                    setKeys(next);
                  }}
                >
                  Move later
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={keys.length <= 2}
                  onClick={() => setKeys(keys.filter((_, i) => i !== index))}
                >
                  Remove
                </Button>
              </div>
            </Field>
          ))}
          <FieldDescription>{`[ ${keys.map((k) => `{{${k}}}`).join(" | ")} ]`}</FieldDescription>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setKeys([...keys, variables[0]])}
            >
              Add variable
            </Button>
            <Button
              type="button"
              onClick={() => {
                insert(`[ ${keys.map((k) => `{{${k}}}`).join(" | ")} ]`);
                setOpen(false);
              }}
            >
              Insert expression
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
