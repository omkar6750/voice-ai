export type ParameterRow = {
  name: string;
  originalName?: string;
  type: string;
  description: string;
  required: boolean;
};

export function parameterRows(
  parameters: Record<string, unknown>,
): ParameterRow[] {
  const schema = parameters as {
    properties?: Record<string, Record<string, unknown> | boolean>;
    required?: string[];
  };
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([name, value]) => ({
    name,
    originalName: name,
    type:
      typeof value === "object" && typeof value.type === "string"
        ? value.type
        : "",
    description:
      typeof value === "object" && typeof value.description === "string"
        ? value.description
        : "",
    required: required.has(name),
  }));
}

// Keep enums, nested schemas, references, defaults, and root constraints.
export function parametersSchema(
  rows: ParameterRow[],
  original: Record<string, unknown>,
): Record<string, unknown> {
  const old = (original.properties ?? {}) as Record<
    string,
    Record<string, unknown> | boolean
  >;
  const properties: Record<string, Record<string, unknown> | boolean> = {};
  const required = ((original.required ?? []) as string[]).filter(
    (name) => !Object.hasOwn(old, name),
  );
  for (const row of rows) {
    const name = row.name.trim();
    if (!name) throw new Error("Every parameter needs a name.");
    if (Object.hasOwn(properties, name))
      throw new Error("Parameter names must be unique.");
    const previous = old[row.originalName ?? ""] ?? {};
    const previousObject = typeof previous === "boolean" ? {} : previous;
    const property = { ...previousObject };
    if (row.type && row.type !== previousObject.type) property.type = row.type;
    if (row.description !== (previousObject.description ?? ""))
      property.description = row.description;
    Object.defineProperty(properties, name, {
      value:
        typeof previous === "boolean" && !row.type && !row.description
          ? previous
          : property,
      enumerable: true,
      configurable: true,
      writable: true,
    });
    if (row.required) required.push(name);
  }
  const result: Record<string, unknown> = { ...original, properties };
  if (!Object.hasOwn(original, "properties") && !rows.length)
    delete result.properties;
  if (required.length) return { ...result, required };
  if (Object.hasOwn(original, "required")) result.required = [];
  else delete result.required;
  return result;
}

export function parseSchema(value: string): Record<string, unknown> {
  const schema: unknown = JSON.parse(value);
  if (!schema || typeof schema !== "object" || Array.isArray(schema))
    throw new Error("Input schema must be a JSON object.");
  return schema as Record<string, unknown>;
}
