import test from "node:test";
import assert from "node:assert/strict";
import { selectTtsModel } from "../src/pages/agents/speech-model.ts";

test("v3 to v4 requires explicit persona without mutating saved configuration", () => {
  const published = Object.freeze({provider: "sarvam", model: "bulbul:v3", voice: "ritu", language: "en-IN", pace: 1, sarvam: null});
  const draft = selectTtsModel(published, "bulbul:v4-flash");
  assert.equal(draft.voice, "");
  assert.equal(draft.sarvam.min_buffer_size, 30);
  assert.equal(published.voice, "ritu");
  assert.equal(published.model, "bulbul:v3");
});
test("switching back cannot retain a persona or unsupported v4 settings", () => {
  const draft = selectTtsModel({provider: "sarvam", model: "bulbul:v4-flash", voice: "ritu_hi_customer", sarvam: {pitch: 0.2}}, "bulbul:v3");
  assert.equal(draft.voice, "");
  assert.equal(draft.sarvam, null);
});
test("same model does not clear the saved voice", () => {
  const saved = {provider: "sarvam", model: "bulbul:v3", voice: "ritu"};
  assert.equal(selectTtsModel(saved, saved.model), saved);
});
