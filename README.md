# claw-my-marketplace

OpenClaw-native **skills + wiring** for the Onion-AI exec agents (`lukas-assist`,
`lukas-double`) that run on the **Codex harness** (`openai/gpt-5.5` via ChatGPT
subscription) inside `microk8s-onion`.

It is the OpenClaw counterpart to
[`codex-my-marketplace`](https://github.com/lukaskellerstein/codex-my-marketplace),
which targets Claude Code / Codex. **The skills are not rewritten here** — they
are *generated* from that repo by `tools/migrate_skills.py`, so the prose stays
single-source. This repo adds only the OpenClaw-specific wiring that a Codex
bundle install would otherwise drop.

## Why this repo exists (the Codex-harness constraint)

A codex-harness OpenClaw agent is extended through exactly three surfaces:

1. **Skills** — AgentSkills `SKILL.md` folders, loaded via `skills.load.extraDirs`.
   `user-invocable` skills also become `/slash` commands.
2. **MCP — via Codex's own config** (`codex mcp add` into `CODEX_HOME`), **not**
   `openclaw.json`. OpenClaw only surfaces `openclaw.json` / bundle MCP to its
   *embedded* agent; a codex-harness turn runs inside a Codex app-server thread.
3. **Subagents** — `sessions_spawn` + `agents.list[]` config (not `agents/*.md`).

What does **not** work for these bots, and why we don't use it:

- **Native Codex plugins** (`openclaw migrate codex`): V1 only activates
  `openai-curated` marketplace plugins that were source-installed. A custom git
  marketplace can never be enabled this way. Hard dead end.
- **Installing `codex-my-marketplace` as a bundle**: OpenClaw auto-detects the
  `.codex-plugin/plugin.json` Codex bundle, but for a **codex-harness** bot a
  Codex bundle contributes **only its skills** — its `.mcp.json` targets the
  embedded agent, its `hooks.json`/bash hooks are detect-only (and OpenClaw
  `PostToolUse` hooks never see Codex's internal file writes anyway), and its
  `agents/*.md` are detect-only. So a bundle install ≠ working media/office
  stack. We map each concern to the primitive that actually reaches the harness.

See `docs/architecture.md` for the full mapping table and citations.

## Layout

```
claw-my-marketplace/
├── skills/                  # GENERATED OpenClaw skills (media + office). Do not hand-edit.
├── skills.manifest.json     # which source skills to include + per-skill OpenClaw gating
├── tools/
│   └── migrate_skills.py    # regenerates skills/ from a codex-my-marketplace checkout
├── codex-mcp/
│   └── servers.json         # MCP servers the pod registers via `codex mcp add`
├── toolchain/
│   └── install.sh           # idempotent pod-side toolchain installer for the kept skills
├── subagents/
│   └── media-director/      # OpenClaw agents.list[] role + workspace md
├── bin/                     # exec-invoked helpers (drawio edge-routing postprocessor, svg check)
└── docs/
    ├── architecture.md      # decision record + OpenClaw mapping
    └── consume-in-nuc-server.md  # how the exec-agents deployment pulls this repo
```

## Regenerate the skills

```bash
# default source: ~/Projects/Github/lukaskellerstein/codex-my-marketplace
python3 tools/migrate_skills.py
# or point at a specific checkout:
python3 tools/migrate_skills.py --source /path/to/codex-my-marketplace
```

The script is deterministic: same source → same `skills/`. Commit the result.

## How the pod consumes it

The exec-agents init container clones this repo and:

1. copies `skills/*` onto the PVC under `~/.openclaw/plugin-skills` (already an
   `skills.load.extraDirs` entry),
2. runs `toolchain/install.sh` to install the bins/libs the gated skills need,
3. registers `codex-mcp/servers.json` with `codex mcp add`,
4. (optional) merges `subagents/*` into `agents.list[]` + the workspace.

Full wiring + the proposed `base/deployment.yaml` diff: `docs/consume-in-nuc-server.md`.

## Scope

Active now: **media** + **office**. `design` and `web-design` skills are
intentionally excluded from `skills.manifest.json` until their pod toolchains
(browser MCP fleet, Vite build, multi-agent orchestration) are wired.
