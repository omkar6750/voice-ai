import type { AgentConfig } from "./types";

export const sarvamDefaults = {
  pitch: null,
  loudness: null,
  enable_preprocessing: null,
  temperature: null,
  min_buffer_size: null,
  max_chunk_length: null,
};

export function selectTtsModel(
  tts: AgentConfig["tts"],
  model: string,
): AgentConfig["tts"] {
  if (model === tts.model) return tts;
  return {
    ...tts,
    model,
    ...(tts.provider === "sarvam"
      ? {
          voice: "",
          sarvam:
            model === "bulbul:v4-flash"
              ? {
                  ...sarvamDefaults,
                  min_buffer_size: 30,
                  max_chunk_length: 150,
                }
              : null,
        }
      : {}),
  };
}
