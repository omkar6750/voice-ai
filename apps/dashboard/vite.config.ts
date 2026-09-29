import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VOICE_");
  const repoRoot = fileURLToPath(new URL("../../", import.meta.url));
  const clerkPublicKey = process.env.VITE_CLERK_PUBLISHABLE_KEY ?? loadEnv(mode, repoRoot, "CLERK_PUBLISHABLE_KEY").CLERK_PUBLISHABLE_KEY;
  const publicHost = env.VOICE_PUBLIC_BASE_URL ? new URL(env.VOICE_PUBLIC_BASE_URL).hostname : undefined;
  return {
  plugins: [react(), tailwindcss()],
  define: {
    "import.meta.env.VITE_CLERK_PUBLISHABLE_KEY": JSON.stringify(clerkPublicKey ?? ""),
  },
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: env.VOICE_API_ORIGIN ?? "http://127.0.0.1:8000",
        ws: true,
      },
    },
    host: "0.0.0.0",
    allowedHosts: [
      ...(publicHost ? [publicHost] : []),
    ],
  }
  };
});
