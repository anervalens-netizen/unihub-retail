#!/usr/bin/env node
/* global process */
import fs from "node:fs";

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
process.stdout.write(`Dependency policy valid; nanoid=${installedNanoid}\n`);
