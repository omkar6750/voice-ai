// Deployment build guard; no dashboard application code lives here.
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

const publicKeys = [
  "VITE_CLERK_PUBLISHABLE_KEY",
  "VITE_API_ORIGIN",
  "VITE_CLERK_SIGN_IN_URL",
  "VITE_CLERK_SIGN_UP_URL",
  "VITE_CLERK_AFTER_SIGN_IN_URL",
  "VITE_CLERK_AFTER_SIGN_UP_URL",
  "VITE_CLERK_ORGANIZATION_PROFILE_URL",
  "VITE_CLERK_CREATE_ORGANIZATION_URL",
  "VITE_CLERK_INVITATION_REDIRECT_URL",
];
const unexpected = Object.keys(process.env).filter(
  (key) => key.startsWith("VITE_") && !publicKeys.includes(key),
);
function fail(message) {
  console.error(message); // Never print environment values.
  process.exit(1);
}
if (unexpected.length) fail("Unexpected VITE variable: public build allowlist violated");
// Vite loads these itself. Reject them without reading any dotenv contents.
if ([".env", ".env.local", ".env.production", ".env.production.local"].some(existsSync)) {
  fail("Dotenv files are forbidden in the hosted dashboard build");
}
if (!/^pk_(test|live)_\S+$/.test(process.env.VITE_CLERK_PUBLISHABLE_KEY ?? "")) {
  fail("A public Clerk publishable key is required");
}
let origin;
try {
  origin = new URL(process.env.VITE_API_ORIGIN);
} catch {
  fail("An HTTPS API origin is required");
}
if (
  origin.protocol !== "https:" || origin.username || origin.password ||
  origin.pathname !== "/" || origin.search || origin.hash
) fail("API origin must be HTTPS without credentials, path, query, or fragment");

// Backend credentials cannot reach npm or Vite through inherited process env.
const buildEnv = {};
for (const key of ["PATH", "HOME", "TMPDIR", "TEMP", "TMP", "SystemRoot", "COMSPEC", "CI", ...publicKeys]) {
  if (process.env[key] !== undefined) buildEnv[key] = process.env[key];
}
// Local acceptance can validate policy without installing/building anything.
if (process.argv.includes("--validate-only")) process.exit(0);
for (const args of [["ci"], ["run", "build"]]) {
  const result = spawnSync("npm", args, { env: buildEnv, stdio: "inherit" });
  if (result.error || result.status !== 0) fail("Hosted dashboard build failed");
}
