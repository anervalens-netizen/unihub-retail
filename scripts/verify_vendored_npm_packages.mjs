import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const lock = JSON.parse(readFileSync("package-lock.json", "utf8"));
const packageJson = JSON.parse(readFileSync("package.json", "utf8"));

const packages = [
  "api-client",
  "design-tokens",
  "types",
  "ui-kit",
];

for (const shortName of packages) {
  const packageName = `@unihub/${shortName}`;
  const lockEntry = lock.packages[`node_modules/${packageName}`];
  if (!lockEntry) {
    throw new Error(`Missing lock entry for ${packageName}`);
  }

  const expectedPath = `vendor/npm/unihub-${shortName}-${lockEntry.version}.tgz`;
  const expectedSpec = `file:${expectedPath}`;
  if (packageJson.dependencies?.[packageName] !== expectedSpec) {
    throw new Error(`${packageName} must use ${expectedSpec}`);
  }
  if (lock.packages[""].dependencies?.[packageName] !== expectedSpec) {
    throw new Error(`Root lock entry for ${packageName} must use ${expectedSpec}`);
  }
  if (lockEntry.resolved !== expectedSpec) {
    throw new Error(`Resolved lock entry for ${packageName} must use ${expectedSpec}`);
  }

  const actualIntegrity = `sha512-${createHash("sha512")
    .update(readFileSync(expectedPath))
    .digest("base64")}`;
  if (actualIntegrity !== lockEntry.integrity) {
    throw new Error(`Integrity mismatch for ${packageName}`);
  }
}

if (readFileSync("package-lock.json", "utf8").includes("127.0.0.1:4873")) {
  throw new Error("package-lock.json still depends on host-local Verdaccio");
}
