# Architecture & decision record

## The question

We want the exec-agent bots (`lukas-assist`, `lukas-double`) to have the
capabilities of the `codex-my-marketplace` plugins — **media**, **office**,
design, web-design. Those plugins are Claude Code / Codex bundles
(`skills/`, `agents/`, `commands/`, `hooks/`, `.mcp.json`). How do we get that
functionality into OpenClaw bots that run the **Codex harness**?

## The binding constraint: the Codex harness

The bots run `openai/gpt-5.5` through the bundled `codex` plugin
(`plugins.entries.codex.enabled`). A codex-harness turn executes inside a **Codex
app-server thread**, not OpenClaw's embedded agent loop. That single fact governs
which extension surfaces actually reach the model:

| Surface | Reaches a codex-harness turn? | How |
| --- | --- | --- |
| **Skills** (`SKILL.md`) | ✅ | `skills.load.extraDirs` → injected skill catalog; `user-invocable` ⇒ `/slash` |
| **MCP** | ✅ but only via **Codex's** config | `codex mcp add` into `CODEX_HOME`. `openclaw.json`/bundle MCP feeds the *embedded* agent only |
| **Subagents** | ✅ | `sessions_spawn` + `agents.list[]` (config, not `agents/*.md`) |
| **Hooks** | ❌ (effectively) | OpenClaw `PostToolUse` hooks fire on OpenClaw's own tools; Codex's `apply_patch`/file writes happen inside the Codex thread, invisible to them |
| **Slash commands** (`commands/*.md`) | ⚠️ | not a Codex-bundle feature; redundant — `user-invocable` skills already are slash commands |

### Why the two "obvious" routes don't work

- **Native Codex plugins** (`openclaw migrate codex` → `codexPlugins`):
  *"V1 supports only `openai-curated` plugins that migration observed as
  source-installed"* (`docs/plugins/codex-native-plugins.md`). A custom git
  marketplace is never eligible. Dead end.
- **Install `codex-my-marketplace` as a bundle** (`openclaw plugins install
  git:…`): OpenClaw detects the `.codex-plugin/plugin.json` Codex bundle, but per
  `docs/plugins/bundles.md` a Codex bundle contributes **skills + OpenClaw-style
  hook-packs + MCP-for-the-embedded-agent** only. For a codex-harness bot that
  collapses to *just the skills* — the `.mcp.json` targets the wrong agent, the
  `hooks.json` is detect-only (and couldn't see Codex's writes anyway), and
  `agents/*.md` are detect-only. So a bundle install ≠ a working stack.

**Conclusion:** the portable core is the **skills**; everything else must be
re-mapped to the primitive that reaches the harness. That re-mapping is this repo.

## What this repo does, per concern

- **Skills** → `tools/migrate_skills.py` generates `skills/` from the source
  marketplace, applying three mechanical fixes OpenClaw needs:
  1. single-line `name`/`description` + single-line `metadata.openclaw` (the
     embedded parser rejects YAML block scalars / multi-line metadata);
  2. `metadata.openclaw.requires` gating so a skill only appears when its
     bins/env exist in the pod (no more "loaded but unusable");
  3. `${CLAUDE_PLUGIN_ROOT}/skills/` → `{baseDir}/../` (skills are flat siblings
     under one extraDirs root), and `${CLAUDE_PLUGIN_ROOT}/…` → the
     `_office-shared/` sibling.
- **MCP** → `codex-mcp/servers.json`, consumed by `codex mcp add`. Drops the
  GUI-only drawio MCP; keeps media-mcp / elevenlabs / mermaid / playwright.
- **Hooks** → **not needed.** The skills already invoke their postprocessors as
  explicit exec steps (e.g. graph-generation: *"Postprocessing is MANDATORY …
  run `node …/postprocess.js <file> <file>`"*). That is the correct pattern for
  the Codex harness; the auto-hook was only a Claude-Code convenience.
- **Subagents** → `subagents/media-director/` (one `agents.list[]` role +
  workspace `AGENTS.md`/`TOOLS.md`). Media/office are largely single-agent, so we
  wire only the one orchestrator that adds value now.
- **Toolchain** → `toolchain/install.sh` installs exactly what the *kept, gated*
  skills need, so gating predicates pass.

## Skill-by-skill gating (media + office)

| Skill | Gate (`metadata.openclaw.requires`) | Why |
| --- | --- | --- |
| visual-planning, media-prompt-craft | always | pure-text gates/helpers |
| icon-library, image-sourcing, svg-mastery | always | web fetch / knowledge |
| image/video/music-generation | `bins:[uv]`, `env:[GEMINI_API_KEY]` | media-mcp (uvx) + Gemini key |
| speech-generation | `bins:[uv]`, `env:[ELEVENLABS_API_KEY]` | elevenlabs-mcp + key |
| graph-generation | `bins:[node]` | D3 + drawio postprocessor (node) |
| docx, pptx | `bins:[node]` | docx-js / pptxgenjs generation |
| xlsx | `bins:[uv]` | openpyxl (python via uv venv) |

LibreOffice (`soffice`) is deliberately **not** installed — the office skills
already skip their thumbnail/PDF/recalc QA when it's absent. Generation
(node) and OOXML unpack/pack/validate (python `lxml`) work without it.

## Out of scope (for now)

`design` and `web-design` skills are excluded from `skills.manifest.json`. Web
design in particular needs a browser-MCP fleet, a Vite/React build environment,
and real multi-agent orchestration (page-builder + visual-fixer) in-pod — a
larger toolchain + subagent effort to be done deliberately later.
