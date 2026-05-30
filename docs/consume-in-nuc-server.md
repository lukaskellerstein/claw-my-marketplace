# Consuming this repo in the exec-agents deployment

Target: `onion-ai-eu/nuc-server` → `exec-agents/lukas-ond/base/deployment.yaml`
(`init-tools` container) + the overlays' `openclaw.json` + persona `*.md`.

The current `init-tools` already does most of this **hand-rolled** against
`codex-my-marketplace` (clone → `cp skills/*`, `codex mcp add` for
media-mcp/elevenlabs/mermaid). This repo replaces those ad-hoc blocks with a
single declarative source. Nothing below is applied automatically — it is the
change set to review before touching the production bots.

## 1. init-tools: source skills + toolchain from this repo

Replace the "Marketplace plugin SKILLS" clone block with a clone of
**claw-my-marketplace** and a call to its installer:

```sh
PLUGIN_SKILLS_DIR="/home/node/.openclaw/plugin-skills"
MARKET_URL="https://github.com/lukaskellerstein/claw-my-marketplace"
CLAW_VERSION="claw-1"   # bump to force a re-pull after a marketplace change
if [ ! -f "$PLUGIN_SKILLS_DIR/.installed-${CLAW_VERSION}" ]; then
  rm -rf /tmp/claw "$PLUGIN_SKILLS_DIR"
  if git clone --depth 1 "$MARKET_URL" /tmp/claw 2>/dev/null; then
    mkdir -p "$PLUGIN_SKILLS_DIR"
    cp -r /tmp/claw/skills/* "$PLUGIN_SKILLS_DIR"/        # includes _office-shared (no SKILL.md -> not scanned)
    # toolchain for the gated skills (office node libs, skill node deps, office python venv)
    SKILLS_DIR="$PLUGIN_SKILLS_DIR" \
      DOCTOOLS_DIR="/home/node/.openclaw/doctools" \
      OFFICE_VENV="/home/node/.openclaw/office-venv" \
      BIN_DIR="$BIN_DIR" \
      sh /tmp/claw/toolchain/install.sh || echo "init-tools: claw toolchain install degraded"
    # codex MCP servers from the manifest (replaces the hand-written codex mcp add block)
    CLAW_REPO=/tmp/claw CODEX_BIN=/app/node_modules/.bin/codex \
      UV_ENV="$UVENV" node /tmp/claw/toolchain/register-codex-mcp.mjs || true
    cp -r /tmp/claw/subagents "/home/node/.openclaw/subagents-src" 2>/dev/null || true
    touch "$PLUGIN_SKILLS_DIR/.installed-${CLAW_VERSION}"
  else
    echo "init-tools: claw-my-marketplace clone failed; continuing"
  fi
fi
```

Notes:
- `DOCTOOLS_DIR` is the same dir already on `NODE_PATH`, so `install.sh` step 1
  supersedes the inline `doctools` block in the current deployment — remove that
  block to avoid two sources of truth.
- `install.sh` already runs `npm install` for the drawio postprocessor and the
  svg-mastery scripts, so the agent never builds them mid-task.
- `OFFICE_VENV/bin` should be added to the login-shell PATH (the
  `gws-path-profile` `/etc/profile.d` snippet) so `python3` in the xlsx/editing
  skills resolves openpyxl. Alternatively the skills can call
  `$OFFICE_VENV/bin/python`.
- `register-codex-mcp.mjs` reads `codex-mcp/servers.json` and emits the `codex
  mcp add` calls with the pod's `UV_*`/PATH `--env` flags (passed via `UV_ENV`),
  skipping stdio servers whose `requires` env is unset. It supersedes the
  deployment's inline `codex mcp add` block; the only behavioural delta is adding
  `media-playwright`.

## 2. openclaw.json (overlays/<bot>/config)

- `skills.load.extraDirs` already includes `/home/node/.openclaw/plugin-skills` — no change.
- To enable the **media-director** subagent, merge `subagents/media-director/agent.json`
  into `agents.list[]` and copy its `workspace/` to `~/.openclaw/subagents/media-director`
  (init-tools `cp` above stages it under `subagents-src`; add a copy into place).
  The main agent also needs `sessions_spawn` — set `tools.profile: "coding"` (or
  `tools.alsoAllow: ["sessions_spawn","sessions_yield","subagents"]`). Optionally
  set `agents.defaults.subagents.model` to run the director cheaper.
- Keep the codex media tool exclusions as-is (`image_generate`/`video_generate`
  excluded so the agent routes to media-mcp).

## 3. Personas: make TOOLS.md defer to skills

The current `overlays/*/workspace/TOOLS.md` hand-describes a `pptxgenjs/docx/exceljs`
node-script flow that **competes** with the office skills (which now ship here and
own the *how*). Slim TOOLS.md to bot-specific *policy* and point at the skills:

- Remove the "Generating documents (PowerPoint / Word / Excel)" how-to block —
  the `docx`/`pptx`/`xlsx` skills own it.
- Replace with one line: *"Documents and media: use the `docx`/`pptx`/`xlsx` and
  media skills (image/graph/speech/…). They own the workflow; follow them."*
- Keep the gws/`gh`/Slack/memory policy sections (those are bot policy, not skill
  content).

## 4. Verify (per `.claude/rules/06-testing.md`)

After applying, on a Ready pod:

```sh
# skills load + gate correctly (gated ones appear only when keys present)
kubectl -n exec-agents exec deploy/lukas-assist -c gateway -- \
  node /app/dist/index.js skills list | grep -E 'docx|pptx|xlsx|image-generation|graph-generation'
# codex sees the MCP servers
kubectl -n exec-agents exec deploy/lukas-assist -c gateway -- \
  /app/node_modules/.bin/codex mcp list
# office python venv present
kubectl -n exec-agents exec deploy/lukas-assist -c gateway -- \
  /home/node/.openclaw/office-venv/bin/python -c 'import openpyxl, lxml; print("ok")'
```

Then a live smoke test in Slack DM: *"make me a 3-slide deck about X"* (pptx),
*"generate an image of …"* (image-generation via media-mcp), *"diagram our auth
flow"* (graph-generation → drawio postprocess).
