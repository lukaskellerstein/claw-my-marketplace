#!/usr/bin/env node
// Register this repo's codex-mcp/servers.json with the Codex app-server, so a
// codex-harness OpenClaw agent can see the media MCP tools. Codex-harness turns
// only see MCP through Codex's own config (CODEX_HOME), NOT openclaw.json.
//
// Idempotent (remove + add per server). A stdio server is skipped when any of
// its `requires` env vars is unset. An http server is always added.
//
// Env contract:
//   CODEX_BIN   path to the codex binary (default: /app/node_modules/.bin/codex)
//   CODEX_HOME  codex home on the PVC (codex reads it from env; we just pass through)
//   CLAW_REPO   path to this repo checkout (default: dir two levels up)
//   UV_ENV      optional space-separated `--env K=V` flags appended to stdio adds
//               (the pod redirects all uv/PATH dirs onto the PVC)
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const repo = process.env.CLAW_REPO || dirname(dirname(fileURLToPath(import.meta.url)));
const codex = process.env.CODEX_BIN || "/app/node_modules/.bin/codex";
const uvEnv = (process.env.UV_ENV || "").trim();
const uvFlags = uvEnv ? uvEnv.split(/\s+/) : [];

const { servers } = JSON.parse(readFileSync(join(repo, "codex-mcp/servers.json"), "utf8"));

const run = (args) => {
  const r = spawnSync(codex, args, { encoding: "utf8" });
  return r.status === 0;
};

let added = 0;
for (const [name, def] of Object.entries(servers)) {
  if (name.startsWith("$")) continue;
  const missing = (def.requires || []).filter((k) => !process.env[k]);
  if (missing.length) {
    console.log(`register-codex-mcp: skip ${name} (unset: ${missing.join(", ")})`);
    continue;
  }
  run(["mcp", "remove", name]); // best-effort; ignore if absent

  let args;
  if (def.type === "http") {
    args = ["mcp", "add", name, "--url", def.url];
  } else {
    const envFlags = (def.env || [])
      .filter((k) => process.env[k] !== undefined)
      .flatMap((k) => ["--env", `${k}=${process.env[k]}`]);
    args = ["mcp", "add", name, ...envFlags, ...uvFlags, "--", def.command, ...(def.args || [])];
  }
  if (run(args)) {
    added += 1;
    console.log(`register-codex-mcp: added ${name}`);
  } else {
    console.log(`register-codex-mcp: FAILED to add ${name}`);
  }
}
console.log(`register-codex-mcp: ${added} server(s) registered`);
