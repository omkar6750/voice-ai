import { Field, FieldLabel } from "@/components/ui/field";

import { NativeSelect } from "@/components/ui/native-select";

import type { FlowNode, ProviderCatalog } from "./types";

type Branch = Exclude<
  FlowNode["functions"][number]["transition_to"],
  string | null
>;

export function LeadClassifierRouting({
  branch,
  onChange,
  nodeIds,
  disabled,
  contract,
}: {
  branch: Branch;

  onChange: (branch: Branch) => void;

  nodeIds: string[];

  disabled: boolean;

  contract?: ProviderCatalog["classifier_contract"];
}) {
  const fields = contract?.fields;

  if (!fields)
    return (
      <p role="alert" className="text-sm text-destructive">
        Classifier routing contract unavailable. Reload the page before editing
        routes.
      </p>
    );

  const options = Object.entries(fields).filter(
    ([field]) =>
      field !== "followup_route" || branch.field === "followup_route",
  );

  const values = fields[branch.field] ?? [];

  return (
    <section className="grid gap-3" aria-label="Classifier result routing">
      <Field>
        <FieldLabel>Result field</FieldLabel>
        <NativeSelect
          aria-label="Classifier result field"
          value={branch.field}
          disabled={disabled}
          onChange={(event) =>
            onChange({ ...branch, field: event.target.value, cases: {} })
          }
        >
          {options.map(([field]) => (
            <option key={field} value={field}>
              {field === "classification_key"
                ? "All three answers (27 combinations)"
                : field}
            </option>
          ))}
        </NativeSelect>
      </Field>

      <p className="text-xs text-muted-foreground">
        Choose the next node for each result. Unassigned cases use the default
        below. Combination order: temperature · service fit · tone.
      </p>

      <div className="grid max-h-96 gap-2 overflow-y-auto">
        {values.map((value) => (
          <Field key={value} className="grid gap-1">
            <FieldLabel>{value.replaceAll("|", " · ")}</FieldLabel>
            <NativeSelect
              aria-label={`Destination for ${value}`}
              value={branch.cases[value] ?? "__default__"}
              disabled={disabled}
              onChange={(event) => {
                const cases = { ...branch.cases };

                if (event.target.value === "__default__") delete cases[value];
                else cases[value] = event.target.value;

                onChange({ ...branch, cases });
              }}
            >
              <option value="__default__">Use default</option>
              {nodeIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </NativeSelect>
          </Field>
        ))}
      </div>

      <Field>
        <FieldLabel>Default destination</FieldLabel>
        <NativeSelect
          aria-label="Classifier default destination"
          value={branch.default ?? "__stay__"}
          disabled={disabled}
          onChange={(event) =>
            onChange({
              ...branch,
              default:
                event.target.value === "__stay__" ? null : event.target.value,
            })
          }
        >
          <option value="__stay__">Stay on this node</option>
          {nodeIds.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </NativeSelect>
      </Field>
    </section>
  );
}
