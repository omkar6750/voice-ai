import { useState } from "react";
import {
  BrainCircuit,
  Cpu,
  Plus,
  RotateCcw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { Textarea } from "@/components/ui/textarea";
import { NumberField } from "./ConfigFields";
import {
  CredentialBindingSelect,
  bindCredential,
} from "./CredentialBindingSelect";
import { OpenRouterModelPicker } from "./OpenRouterModelPicker";
import type { AgentConfig, JevQuestion, ProviderCatalog } from "./types";

const DEFAULT_JEV_QUESTIONS: Record<string, JevQuestion> = {
  lead_temperature: {
    type: "choice",
    instructions:
      "Classify the contact's current sales intent based primarily on their behavior and meaning in the conversation. Voice-call responses are often very short, so do not treat short answers such as 'yeah', 'okay', 'hmm', or 'sure' as negative by themselves. Consider whether the contact has a real need, demonstrates interest in the offering, asks buying-related questions, indicates timing or urgency, or shows resistance. When evidence supports multiple classifications or contains conflicting signals, preserve that uncertainty.",
    criteria: {
      hot: "The contact shows clear current buying intent or meaningful progression toward a purchase. Signals may include confirming a real need, wanting the service soon, asking about price, timeline, implementation, next steps, availability, payment, or requesting a meeting or proposal.",
      warm: "The contact shows genuine interest or relevance but has not demonstrated strong immediate purchase intent. They may listen, answer discovery questions positively, acknowledge a need, or ask general questions, but timing, commitment, urgency, or next-step intent remains uncertain.",
      cold: "The contact demonstrates little current interest or weak relevance. Signals include saying they are only browsing, having no current need, rejecting the offering, repeatedly avoiding engagement, stating bad timing without future intent, or otherwise showing no meaningful movement toward a purchase.",
    },
  },
  service_fit: {
    type: "choice",
    instructions:
      "Determine how closely the contact's actual need matches the service currently being offered (custom modern web & mobile app development).",
    criteria: {
      strong_fit:
        "The contact clearly needs custom web or mobile application development, UI/UX redesign, or secure cloud backends.",
      possible_fit:
        "The need may overlap with the offered service (e.g. existing tech team needing support, adjacent integrations) but requires clarification.",
      poor_fit:
        "The contact needs something materially different (e.g. non-software hardware, marketing-only, or no development needed).",
    },
  },
  tone: {
    type: "choice",
    instructions: "What is the contact's conversational tone and attitude?",
    criteria: {
      receptive: "Friendly, engaged, curious, or actively answering questions.",
      hesitant: "Reserved, busy, distracted, but not hostile.",
      resistant:
        "Disinterested, irritated, abusive, or explicitly asking to stop.",
    },
  },
};

export function ClassifierPanel({
  config,
  change,
  providers,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  providers?: ProviderCatalog | null;
  disabled: boolean;
}) {
  const classifier = config.classifier;
  const classifierType = classifier.classifier_type ?? "llm";
  const currentLlm: NonNullable<typeof classifier.llm> = classifier.llm ?? {
    provider: "groq",
    model: "qwen/qwen3.8-27b",
    temperature: 0.2,
    max_tokens: 256,
    top_p: null,
    reasoning_effort: "none",
    models: [],
    provider_preferences: null,
    prompt: "",
    output_fields: {},
    max_output_tokens: 256,
  };
  const allNodeIds = config.flow.nodes.map((node) => node.id);

  // New question draft state
  const [newQuestionKey, setNewQuestionKey] = useState("");
  const [showAddQuestion, setShowAddQuestion] = useState(false);

  function update(partial: Partial<typeof classifier>) {
    change({
      ...config,
      classifier: {
        ...classifier,
        ...partial,
      },
    });
  }

  function toggleNode(listKey: "node_entries" | "node_exits", nodeId: string) {
    const current = classifier[listKey] ?? [];
    const next = current.includes(nodeId)
      ? current.filter((id) => id !== nodeId)
      : [...current, nodeId];
    update({ [listKey]: next });
  }

  // Jev Questions helpers
  const currentJev: NonNullable<typeof classifier.jev> = classifier.jev ?? {
    model: "jev-latest",
    api_url: "https://api.typesafe.ai/v1/systemone",
    questions: DEFAULT_JEV_QUESTIONS,
    output_fields: [],
  };
  const questionsMap = currentJev.questions || DEFAULT_JEV_QUESTIONS;

  function updateJev(partial: Partial<typeof currentJev>) {
    update({
      jev: {
        ...currentJev,
        ...partial,
      },
    });
  }

  function handleQuestionChange(
    qKey: string,
    field: "instructions",
    value: string,
  ) {
    const existing = questionsMap[qKey];
    if (!existing) return;
    updateJev({
      questions: {
        ...questionsMap,
        [qKey]: {
          ...existing,
          [field]: value,
        },
      },
    });
  }

  function handleCriteriaChange(
    qKey: string,
    choiceKey: string,
    description: string,
  ) {
    const existing = questionsMap[qKey];
    if (!existing) return;
    updateJev({
      questions: {
        ...questionsMap,
        [qKey]: {
          ...existing,
          criteria: {
            ...existing.criteria,
            [choiceKey]: description,
          },
        },
      },
    });
  }

  function handleRemoveCriteria(qKey: string, choiceKey: string) {
    const existing = questionsMap[qKey];
    if (!existing) return;
    const nextCriteria = { ...existing.criteria };
    delete nextCriteria[choiceKey];
    updateJev({
      questions: {
        ...questionsMap,
        [qKey]: {
          ...existing,
          criteria: nextCriteria,
        },
      },
    });
  }

  function handleAddCriteria(qKey: string) {
    const existing = questionsMap[qKey];
    if (!existing) return;
    const baseKey = "new_choice";
    let candidate = baseKey;
    let i = 1;
    while (candidate in existing.criteria) {
      candidate = `${baseKey}_${i++}`;
    }
    updateJev({
      questions: {
        ...questionsMap,
        [qKey]: {
          ...existing,
          criteria: {
            ...existing.criteria,
            [candidate]: "Criteria description for this choice.",
          },
        },
      },
    });
  }

  function handleRemoveQuestion(qKey: string) {
    const next = { ...questionsMap };
    delete next[qKey];
    updateJev({ questions: next });
  }

  function handleAddQuestionSubmit() {
    const key = newQuestionKey
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_]/g, "_");
    if (!key || key in questionsMap) return;
    updateJev({
      questions: {
        ...questionsMap,
        [key]: {
          type: "choice",
          instructions: `Evaluate ${key.replace(/_/g, " ")} based on conversation dialogue.`,
          criteria: {
            positive: "Positive signal observed.",
            neutral: "Neutral or uncertain signal.",
            negative: "Negative signal observed.",
          },
        },
      },
    });
    setNewQuestionKey("");
    setShowAddQuestion(false);
  }

  function handleResetDefaultQuestions() {
    updateJev({ questions: DEFAULT_JEV_QUESTIONS });
  }

  const llmProviders =
    providers?.providers.filter(
      (p) =>
        p.slots.includes("llm") || (p.models_by_slot?.llm?.length ?? 0) > 0,
    ) ?? [];

  const currentProvider = classifier.llm?.provider || "groq";
  const selectedProviderEntry = llmProviders.find(
    (p) => p.provider === currentProvider,
  );
  const availableModels =
    selectedProviderEntry?.models_by_slot?.llm ||
    selectedProviderEntry?.models ||
    [];

  return (
    <div className="flex flex-col gap-8 max-w-5xl">
      {/* Top Switcher: Two Choice Boxes */}
      <div className="flex flex-col gap-3">
        <div>
          <h2 className="text-base font-semibold">Classification Engine</h2>
          <p className="text-xs text-muted-foreground">
            Select one classifier mode for this agent. Each engine operates as a
            distinct runtime tool with independent configuration.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Option 1: LLM Classifier */}
          <div
            onClick={() => !disabled && update({ classifier_type: "llm" })}
            className={`cursor-pointer rounded-lg border-2 p-4 transition-all ${
              classifierType === "llm"
                ? "border-primary bg-primary/5 shadow-sm"
                : "border-border hover:border-muted-foreground/40 bg-card"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div
                  className={`rounded-md p-2 ${
                    classifierType === "llm"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  <Sparkles className="size-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">LLM Classifier</h3>
                  <p className="text-xs text-muted-foreground">
                    Groq / Gemini / OpenRouter
                  </p>
                </div>
              </div>
              <Badge
                variant={classifierType === "llm" ? "default" : "outline"}
                className="text-[11px]"
              >
                {classifierType === "llm" ? "Active" : "Select"}
              </Badge>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Standard LLM prompt-driven classification returning compact
              key-value JSON state through{" "}
              <code className="font-mono text-foreground font-semibold">
                classify_lead
              </code>
              .
            </p>
          </div>

          {/* Option 2: Dedicated Classifier Model (Jev) */}
          <div
            onClick={() => !disabled && update({ classifier_type: "jev" })}
            className={`cursor-pointer rounded-lg border-2 p-4 transition-all ${
              classifierType === "jev"
                ? "border-primary bg-primary/5 shadow-sm"
                : "border-border hover:border-muted-foreground/40 bg-card"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div
                  className={`rounded-md p-2 ${
                    classifierType === "jev"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  <Cpu className="size-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">Classifier Model</h3>
                  <p className="text-xs text-muted-foreground">
                    TypeSafe AI Jev System One
                  </p>
                </div>
              </div>
              <Badge
                variant={classifierType === "jev" ? "default" : "outline"}
                className="text-[11px]"
              >
                {classifierType === "jev" ? "Active" : "Select"}
              </Badge>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Dedicated multi-choice classification engine with normalized
              results through{" "}
              <code className="font-mono text-foreground font-semibold">
                classify_lead
              </code>
              .
            </p>
          </div>
        </div>
      </div>

      {/* Main Configuration Grid */}
      <div className="grid gap-8 lg:grid-cols-2">
        {/* Left Column: Common Cadence & Triggers */}
        <div className="flex flex-col gap-6">
          <div>
            <h2 className="text-base font-semibold">Cadence & Triggers</h2>
            <p className="text-xs text-muted-foreground">
              Configure when the selected classifier engine executes during
              calls.
            </p>
          </div>

          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="classifier-enabled">
                Classifier status
              </FieldLabel>
              <NativeSelect
                id="classifier-enabled"
                value={classifier.enabled ? "enabled" : "disabled"}
                disabled={disabled}
                onChange={(e) =>
                  update({ enabled: e.target.value === "enabled" })
                }
              >
                <NativeSelectOption value="enabled">Enabled</NativeSelectOption>
                <NativeSelectOption value="disabled">
                  Disabled
                </NativeSelectOption>
              </NativeSelect>
            </Field>

            <Field>
              <FieldLabel>Node entry triggers</FieldLabel>
              <FieldDescription>
                Trigger evaluation immediately upon entering any selected flow
                node:
              </FieldDescription>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {allNodeIds.map((id) => {
                  const active = (classifier.node_entries ?? []).includes(id);
                  return (
                    <Badge
                      key={id}
                      variant={active ? "default" : "outline"}
                      className="cursor-pointer select-none"
                      onClick={() =>
                        !disabled && toggleNode("node_entries", id)
                      }
                    >
                      {id}
                    </Badge>
                  );
                })}
              </div>
            </Field>

            <Field>
              <FieldLabel>Node exit triggers</FieldLabel>
              <FieldDescription>
                Trigger evaluation when transitioning away from any selected
                flow node:
              </FieldDescription>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {allNodeIds.map((id) => {
                  const active = (classifier.node_exits ?? []).includes(id);
                  return (
                    <Badge
                      key={id}
                      variant={active ? "default" : "outline"}
                      className="cursor-pointer select-none"
                      onClick={() => !disabled && toggleNode("node_exits", id)}
                    >
                      {id}
                    </Badge>
                  );
                })}
              </div>
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <NumberField
                id="classifier-every-n"
                label="Every N exchanges"
                value={classifier.every_n_exchanges ?? 0}
                min={0}
                max={50}
                disabled={disabled}
                onChange={(val) =>
                  update({ every_n_exchanges: val > 0 ? val : null })
                }
                hint="Runs after each N completed caller exchanges"
              />
            </div>
          </FieldGroup>
        </div>

        {/* Right Column: Engine-Specific Form */}
        <div className="flex flex-col gap-6">
          {classifierType === "llm" ? (
            /* LLM CLASSIFIER FORM */
            <>
              <div>
                <h2 className="text-base font-semibold">
                  LLM Classifier Settings
                </h2>
                <p className="text-xs text-muted-foreground">
                  Custom instructions and LLM model powering the{" "}
                  <code className="font-mono">classify_lead</code> tool.
                </p>
              </div>

              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="classifier-prompt">
                    System prompt & instructions
                  </FieldLabel>
                  <Textarea
                    id="classifier-prompt"
                    rows={5}
                    value={currentLlm.prompt}
                    disabled={disabled}
                    onChange={(e) =>
                      update({ llm: { ...currentLlm, prompt: e.target.value } })
                    }
                    placeholder="Classify the conversation according to observed caller intent..."
                  />
                  <FieldDescription>
                    Instructions provided to the LLM. Should direct returning a
                    compact JSON object.
                  </FieldDescription>
                </Field>

                <div className="grid grid-cols-2 gap-4">
                  <Field>
                    <FieldLabel htmlFor="classifier-provider">
                      Model provider
                    </FieldLabel>
                    <NativeSelect
                      id="classifier-provider"
                      value={currentProvider}
                      disabled={disabled}
                      onChange={(e) =>
                        update({
                          llm: {
                            ...currentLlm,
                            provider: e.target
                              .value as typeof currentLlm.provider,
                            model:
                              providers?.providers.find(
                                (p) => p.provider === e.target.value,
                              )?.models_by_slot?.llm?.[0] || "",
                          },
                        })
                      }
                    >
                      {llmProviders.map((p) => (
                        <NativeSelectOption key={p.provider} value={p.provider}>
                          {p.provider}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                  </Field>

                  {currentProvider === "openrouter" ? (
                    <OpenRouterModelPicker
                      stage="classifier"
                      credentialId={config.credential_refs.classifier}
                      value={currentLlm.model || ""}
                      disabled={disabled}
                      onChange={(model) =>
                        update({ llm: { ...currentLlm, model } })
                      }
                    />
                  ) : (
                    <Field>
                      <FieldLabel htmlFor="classifier-model">Model</FieldLabel>
                      <SearchableSelect
                        id="classifier-model"
                        value={currentLlm.model || availableModels[0] || ""}
                        onChange={(model) =>
                          update({ llm: { ...currentLlm, model } })
                        }
                        options={[
                          ...(!availableModels.includes(currentLlm.model || "")
                            ? [
                                {
                                  value:
                                    currentLlm.model ||
                                    availableModels[0] ||
                                    "",
                                  label: `${currentLlm.model || availableModels[0] || ""} (saved)`,
                                },
                              ]
                            : []),
                          ...availableModels.map((model) => ({
                            value: model,
                            label: model,
                          })),
                        ]}
                        selectionOnly
                        disabled={disabled || !availableModels.length}
                        placeholder="Search models..."
                      />
                    </Field>
                  )}
                </div>
                <CredentialBindingSelect
                  stage="classifier"
                  provider={currentLlm.provider}
                  value={config.credential_refs.classifier}
                  disabled={disabled}
                  change={(id) =>
                    change(bindCredential(config, "classifier", id))
                  }
                />
              </FieldGroup>
            </>
          ) : (
            /* JEV SYSTEM ONE FORM */
            <>
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-semibold">
                    TypeSafe AI Jev Settings
                  </h2>
                  <p className="text-xs text-muted-foreground">
                    Multi-choice questions and criteria evaluated by the{" "}
                    <code className="font-mono">classify_lead</code> tool.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleResetDefaultQuestions}
                  disabled={disabled}
                  className="gap-1 text-xs"
                >
                  <RotateCcw className="size-3" />
                  Reset to SDR
                </Button>
              </div>

              <FieldGroup>
                <CredentialBindingSelect
                  stage="classifier"
                  provider="jev"
                  value={config.credential_refs.classifier}
                  disabled={disabled}
                  change={(id) =>
                    change(bindCredential(config, "classifier", id))
                  }
                />
                <div className="grid grid-cols-2 gap-4">
                  <Field>
                    <FieldLabel htmlFor="jev-model">Jev Model</FieldLabel>
                    <Input
                      id="jev-model"
                      value={currentJev.model}
                      disabled={disabled}
                      onChange={(e) => updateJev({ model: e.target.value })}
                      placeholder="jev-latest"
                      required
                    />
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="jev-url">API Endpoint</FieldLabel>
                    <Input
                      id="jev-url"
                      value={currentJev.api_url}
                      disabled={disabled}
                      onChange={(e) => updateJev({ api_url: e.target.value })}
                      placeholder="https://api.typesafe.ai/v1/systemone"
                      required
                    />
                  </Field>
                </div>

                {/* Questions & Criteria Builder */}
                <div className="flex flex-col gap-4">
                  <div className="flex items-center justify-between">
                    <FieldLabel>
                      Configured Questions ({Object.keys(questionsMap).length})
                    </FieldLabel>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={disabled}
                      onClick={() => setShowAddQuestion(true)}
                      className="gap-1 text-xs"
                    >
                      <Plus className="size-3.5" />
                      Add Question
                    </Button>
                  </div>

                  {showAddQuestion && (
                    <Card className="border-dashed bg-muted/30 p-3">
                      <div className="flex flex-col gap-3">
                        <FieldLabel htmlFor="new-q-name">
                          New Question Key
                        </FieldLabel>
                        <div className="flex gap-2">
                          <Input
                            id="new-q-name"
                            placeholder="e.g. budget_status"
                            value={newQuestionKey}
                            onChange={(e) => setNewQuestionKey(e.target.value)}
                            onKeyDown={(e) =>
                              e.key === "Enter" && handleAddQuestionSubmit()
                            }
                            autoFocus
                          />
                          <Button size="sm" onClick={handleAddQuestionSubmit}>
                            Add
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setShowAddQuestion(false);
                              setNewQuestionKey("");
                            }}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    </Card>
                  )}

                  {Object.entries(questionsMap).map(([qKey, question]) => (
                    <Card key={qKey} className="overflow-hidden">
                      <CardHeader className="bg-muted/40 py-2.5 px-3">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <BrainCircuit className="size-4 text-primary" />
                            <CardTitle className="font-mono text-xs font-semibold">
                              {qKey}
                            </CardTitle>
                          </div>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            disabled={
                              disabled || Object.keys(questionsMap).length <= 1
                            }
                            onClick={() => handleRemoveQuestion(qKey)}
                            title="Remove question"
                          >
                            <Trash2 className="size-3.5 text-muted-foreground hover:text-destructive" />
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent className="flex flex-col gap-3 p-3 text-xs">
                        <div>
                          <FieldLabel className="text-[11px]">
                            Instructions
                          </FieldLabel>
                          <Textarea
                            rows={2}
                            value={question.instructions}
                            disabled={disabled}
                            onChange={(e) =>
                              handleQuestionChange(
                                qKey,
                                "instructions",
                                e.target.value,
                              )
                            }
                            className="mt-1 text-xs"
                          />
                        </div>

                        <div>
                          <div className="flex items-center justify-between pb-1">
                            <span className="text-[11px] font-medium text-muted-foreground">
                              Choices & Criteria (
                              {Object.keys(question.criteria).length})
                            </span>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="h-6 gap-1 px-1.5 text-[11px]"
                              disabled={disabled}
                              onClick={() => handleAddCriteria(qKey)}
                            >
                              <Plus className="size-3" />
                              Add Choice
                            </Button>
                          </div>

                          <div className="flex flex-col gap-2">
                            {Object.entries(question.criteria).map(
                              ([choiceKey, desc]) => (
                                <div
                                  key={choiceKey}
                                  className="flex items-start gap-2 rounded border bg-background/50 p-2"
                                >
                                  <Badge
                                    variant="outline"
                                    className="font-mono text-[10px] mt-0.5 shrink-0"
                                  >
                                    {choiceKey}
                                  </Badge>
                                  <Input
                                    value={desc}
                                    disabled={disabled}
                                    onChange={(e) =>
                                      handleCriteriaChange(
                                        qKey,
                                        choiceKey,
                                        e.target.value,
                                      )
                                    }
                                    className="h-7 text-xs flex-1"
                                  />
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon-xs"
                                    disabled={
                                      disabled ||
                                      Object.keys(question.criteria).length <= 1
                                    }
                                    onClick={() =>
                                      handleRemoveCriteria(qKey, choiceKey)
                                    }
                                    className="mt-0.5"
                                  >
                                    <Trash2 className="size-3 text-muted-foreground hover:text-destructive" />
                                  </Button>
                                </div>
                              ),
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </FieldGroup>
            </>
          )}

          <div className="rounded-md border p-3 text-xs text-muted-foreground">
            <p className="font-medium text-foreground">
              Compact Runtime Output
            </p>
            <p className="mt-1">
              <code className="font-mono text-foreground font-semibold">
                classify_lead
              </code>{" "}
              and automatic node classifiers use the selected backend, extract
              the live transcript automatically, and return clean, compact
              key-value findings.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
