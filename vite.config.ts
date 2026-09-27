import { defineConfig } from "vite";
import { resolve } from "node:path";

// Relative base so the build works from any GitHub Pages sub-path.
export default defineConfig({
  base: "./",
  build: {
    target: "es2022",
    sourcemap: true,
    rollupOptions: {
      input: { main: resolve(__dirname, "index.html"), methods: resolve(__dirname, "methods.html") },
    },
  },
  test: { include: ["src/**/*.test.ts"] },
} as any);
