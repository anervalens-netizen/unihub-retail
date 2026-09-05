#!/usr/bin/env node
/* global process */
import fs from "node:fs";
import { execFileSync } from "node:child_process";

const manifest = JSON.parse(fs.readFileSync("package.json", "utf8"));
const lock = JSON.parse(fs.readFileSync("package-lock.json", "utf8"));
const expectedNanoid = "3.3.18";
if (manifest.overrides?.nanoid !== expectedNanoid) {
  throw new Error(`package.json must pin nanoid override ${expectedNanoid}`);
}
const installedNanoid = lock.packages?.["node_modules/nanoid"]?.version;
if (installedNanoid !== expectedNanoid) {
  throw new Error(`package-lock.json nanoid=${installedNanoid ?? "missing"}, expected ${expectedNanoid}`);
}
for (const [path, entry] of Object.entries(lock.packages ?? {})) {
  const resolved = entry?.resolved;
  if (typeof resolved === "string" && /^(git\+|git:|github:|http:)/i.test(resolved)) {
    throw new Error(`Untrusted dependency transport at ${path}: ${resolved}`);
  }
}

function changedFilesForPullRequest() {
  const eventPath = process.env.GITHUB_EVENT_PATH;
  if (!eventPath || !fs.existsSync(eventPath)) return null;
  const event = JSON.parse(fs.readFileSync(eventPath, "utf8"));
  const baseSha = event.pull_request?.base?.sha;
  if (typeof baseSha !== "string" || !/^[0-9a-f]{40}$/.test(baseSha)) return null;
  const output = execFileSync(
    "git",
    ["diff", "--name-only", `${baseSha}...HEAD`],
    { encoding: "utf8" },
  );
  return new Set(output.split("\n").filter(Boolean));
}

const changed = changedFilesForPullRequest();
if (changed) {
  const requireChanged = (source, generated) => {
    if (changed.has(source) && !changed.has(generated)) {
      throw new Error(
        `${source} changed without regenerated ${generated}; run pip-compile --generate-hashes before this PR can certify`,
      );
    }
  };

  // requirements-dev.lock is compiled from BOTH editable requirement sources.
  requireChanged("backend/requirements.txt", "backend/requirements.lock");
  requireChanged("backend/requirements.txt", "backend/requirements-dev.lock");
  requireChanged("backend/requirements-dev.txt", "backend/requirements-dev.lock");
}

if (process.argv.includes("--pr-diff-only")) {
  process.stdout.write("Dependency PR diff policy valid\n");
  process.exit(0);
}

const python = "backend/venv/bin/python";
if (!fs.existsSync(python)) {
  throw new Error(`${python} is required to validate Python requirement-lock coherence`);
}

// Keep the new executable dependency-policy logic under focused regression
// coverage even though generic changed-line coverage excludes scripts/.
execFileSync(
  python,
  ["-I", "-m", "pytest", "-q", "backend/tests/test_python_requirement_locks.py"],
  { stdio: "inherit" },
);

execFileSync(python, ["-I", "scripts/check_python_requirement_locks.py"], {
  stdio: "inherit",
});

// requirements-dev.lock is the CI environment, but production/release installs
// requirements.lock. Resolve the entire runtime lock from a clean logical state
// so every transitive requirement and hash must be complete and installable.
execFileSync(
  python,
  [
    "-I",
    "-m",
    "pip",
    "install",
    "--disable-pip-version-check",
    "--quiet",
    "--dry-run",
    "--ignore-installed",
    "--require-hashes",
    "-r",
    "backend/requirements.lock",
  ],
  { stdio: "inherit" },
);

process.stdout.write(`Dependency policy valid; nanoid=${installedNanoid}\n`);
