export type PromptToken = {
  start: number;
  end: number;
  expression: string;
  keys: string[];
  fallback: boolean;
  escaped: boolean;
};
const variable = /^\{\{\s*([A-Za-z0-9_.:-]+)\s*\}\}/;
export function parsePrompt(text: string): PromptToken[] {
  const tokens: PromptToken[] = [];
  const offset = (position: number) =>
    Array.from(text.slice(0, position)).length;
  for (let i = 0; i < text.length;) {
    const escaped = text[i] === "\\",
      start = escaped ? i + 1 : i;
    if (text[start] === "[") {
      const end = text.indexOf("]", start + 1);
      const tail = text.slice(start + 1, end < 0 ? text.length : end);
      if (
        tail.trimStart().startsWith("{{") ||
        (tail.includes("|") && tail.includes("{{"))
      ) {
        if (end < 0)
          throw new Error(
            `Unclosed fallback expression at offset ${offset(i)}`,
          );
        const parts = tail.split("|"),
          matches = parts.map((p) =>
            p.trim().match(/^\{\{\s*([A-Za-z0-9_.:-]+)\s*\}\}$/),
          );
        if (parts.length < 2 || matches.some((m) => !m))
          throw new Error(`Invalid fallback expression at offset ${offset(i)}`);
        tokens.push({
          start: offset(i),
          end: offset(end + 1),
          expression: text.slice(i, end + 1),
          keys: matches.map((m) => m![1]),
          fallback: true,
          escaped,
        });
        i = end + 1;
        continue;
      }
    }
    const match = text.slice(start).match(variable);
    if (match) {
      const end = start + match[0].length;
      tokens.push({
        start: offset(i),
        end: offset(end),
        expression: text.slice(i, end),
        keys: [match[1]],
        fallback: false,
        escaped,
      });
      i = end;
      continue;
    }
    if (text.startsWith("{{", start))
      throw new Error(`Invalid variable reference at offset ${offset(i)}`);
    i++;
  }
  return tokens;
}
export function promptErrors(
  text: string,
  variables: string[],
  booleans: string[] = [],
): string[] {
  try {
    return parsePrompt(text)
      .filter((t) => !t.escaped)
      .flatMap((t) =>
        t.keys.flatMap((key) =>
          !variables.includes(key)
            ? [`Unknown prompt variable '${key}' at offset ${t.start}`]
            : t.fallback && booleans.includes(key)
              ? [
                  `Boolean variable '${key}' cannot be used in a fallback expression`,
                ]
              : [],
        ),
      );
  } catch (error) {
    return [(error as Error).message];
  }
}
