import { ReadOnlyValue } from "@/components/record-page";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PromptEditor } from "./PromptEditor";
import type { AgentConfig } from "./types";

export function PromptsPanel({
  config,
  change,
  boundTools,
  registeredTools,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  boundTools: string[];
  registeredTools: string[];
  disabled: boolean;
}) {
  return (
    <section className="flex max-w-3xl flex-col gap-6">
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="persona">Persona</FieldLabel>
          <Input
            id="persona"
            value={config.persona}
            onChange={(event) =>
              change({ ...config, persona: event.target.value })
            }
            disabled={disabled}
          />
        </Field>
        <PromptEditor
          id="system-prompt"
          label="Global system prompt"
          value={config.system_prompt}
          onChange={(system_prompt) => change({ ...config, system_prompt })}
          availableTools={boundTools}
          registeredTools={registeredTools}
          disabled={disabled}
        />
        <PromptEditor
          id="greeting"
          label="Greeting instruction"
          value={config.greeting}
          placeholder="Example: Introduce yourself warmly and ask whether this is a good time to talk."
          onChange={(greeting) => change({ ...config, greeting })}
          availableTools={boundTools}
          registeredTools={registeredTools}
          disabled={disabled}
        />
      </FieldGroup>
      <div>
        <h2 className="text-sm font-semibold">Current language settings</h2>
        <ReadOnlyValue
          label="Default language"
          value={config.language.default_language}
          reason="Language controls are stored, but call-path application needs acceptance tests."
        />
        <ReadOnlyValue
          label="Supported languages"
          value={config.language.supported_languages.join(", ")}
        />
        <ReadOnlyValue
          label="Follow caller"
          value={String(config.language.follow_caller_language)}
        />
        <ReadOnlyValue
          label="Persist caller preference"
          value={String(config.language.persist_requested_language)}
        />
        <ReadOnlyValue
          label="Contact variables"
          value={config.contact_variables.join(", ") || "None"}
        />
      </div>
    </section>
  );
}
