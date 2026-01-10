import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

const SENSITIVE_ENV_VARS = [
  "AUTH0_CLIENT_SECRET",
  "AUTH0_SECRET",
  "OPENAI_API_KEY",
  "DATABASE_URL",
  "JWT_SECRET",
  "NEXTAUTH_SECRET",
  "ADMIN_API_KEY",
];

const MIN_SECRET_LENGTH = 8;
const STATIC_DIR = path.join(process.cwd(), ".next", "static");
const FILE_PATTERN = /\.(js|css|map)$/i;

async function directoryExists(dir) {
  try {
    const stats = await stat(dir);
    return stats.isDirectory();
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

async function collectFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await collectFiles(fullPath)));
    } else if (FILE_PATTERN.test(entry.name)) {
      files.push(fullPath);
    }
  }

  return files;
}

async function main() {
  const secrets = SENSITIVE_ENV_VARS.flatMap((name) => {
    const value = process.env[name];
    if (typeof value === "string" && value.length >= MIN_SECRET_LENGTH) {
      return [[name, value]];
    }
    return [];
  });

  if (secrets.length === 0) {
    return;
  }

  const hasStaticDir = await directoryExists(STATIC_DIR);
  if (!hasStaticDir) {
    return;
  }

  const files = await collectFiles(STATIC_DIR);
  const matches = new Map();

  for (const file of files) {
    const content = await readFile(file, "utf8");
    for (const [name, value] of secrets) {
      if (content.includes(value)) {
        if (!matches.has(name)) {
          matches.set(name, new Set());
        }
        matches.get(name).add(path.relative(process.cwd(), file));
      }
    }
  }

  if (matches.size > 0) {
    console.error("Sensitive env vars detected in client assets:");
    for (const [name, filesWithSecret] of matches.entries()) {
      for (const filePath of filesWithSecret) {
        console.error(`- ${name} found in ${filePath}`);
      }
    }
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error("Secret scanning failed:", error);
  process.exitCode = 1;
});
