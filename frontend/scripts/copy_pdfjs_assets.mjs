#!/usr/bin/env node
import { cp, mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

async function ensureExists(p) {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

async function copyDir(src, dest) {
  const exists = await ensureExists(src);
  if (!exists) {
    throw new Error(`[copy_pdfjs_assets] Missing source: ${src}`);
  }
  await mkdir(path.dirname(dest), { recursive: true });
  await cp(src, dest, { recursive: true });
}

async function main() {
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const frontendRoot = path.resolve(scriptDir, "..");
  const nodeModules = path.join(frontendRoot, "node_modules", "pdfjs-dist");
  const publicDir = path.join(frontendRoot, "public");

  const tasks = [
    {
      src: path.join(nodeModules, "cmaps"),
      dest: path.join(publicDir, "pdfjs", "cmaps"),
    },
    {
      src: path.join(nodeModules, "standard_fonts"),
      dest: path.join(publicDir, "pdfjs", "standard_fonts"),
    },
  ];

  for (const task of tasks) {
    await copyDir(task.src, task.dest);
    console.log(
      `[copy_pdfjs_assets] Copied ${path.relative(
        frontendRoot,
        task.src,
      )} -> ${path.relative(frontendRoot, task.dest)}`,
    );
  }
}

main().catch((err) => {
  console.error("[copy_pdfjs_assets] Failed:", err);
  process.exit(1);
});
