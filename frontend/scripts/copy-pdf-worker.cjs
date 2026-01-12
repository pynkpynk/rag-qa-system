#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

function findWorkerSource(root) {
  const candidates = [
    path.join(root, "build", "pdf.worker.min.mjs"),
    path.join(root, "build", "pdf.worker.mjs"),
    path.join(root, "legacy", "build", "pdf.worker.min.js"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function main() {
  try {
    const pkgPath = require.resolve("pdfjs-dist/package.json");
    const distRoot = path.dirname(pkgPath);
    const workerSource = findWorkerSource(distRoot);
    if (!workerSource) {
      console.error(
        "[copy-pdf-worker] Failed: unable to locate pdfjs worker under",
        distRoot,
      );
      process.exit(1);
    }

    const publicDir = path.join(__dirname, "..", "public");
    const destPath = path.join(publicDir, "pdf.worker.min.mjs");
    fs.mkdirSync(publicDir, { recursive: true });
    fs.copyFileSync(workerSource, destPath);
    console.log(
      `[copy-pdf-worker] Copied ${path.relative(
        process.cwd(),
        workerSource,
      )} -> ${path.relative(process.cwd(), destPath)}`,
    );
  } catch (err) {
    console.error("[copy-pdf-worker] Failed:", err);
    process.exit(1);
  }
}

main();
