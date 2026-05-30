# TOOLS — media-director

Conventions for this subagent. The *how* lives in the skills; this is policy.

- **Media generation is via Codex MCP tools** (registered by the pod from
  `codex-mcp/servers.json`): image/video/music through `media-mcp`, speech
  through `elevenlabs`, Mermaid via the hosted `mermaid` server, D3 rendering via
  `media-playwright`. If a tool is missing, the relevant API key/server is not
  configured on this pod — say so, don't fake the asset.
- **Always run the `visual-planning` skill before any generation call.** It is
  the pre-generation gate.
- **Diagrams/charts never go through `generate_image`** — route them to the
  `graph-generation` skill (D3 / Mermaid / Draw.io), which renders crisp,
  labelled output and runs the mandatory edge-routing postprocess step.
- **Write outputs under** `~/.openclaw/workspace/media-out` (the attachment-safe
  root) so the parent agent can send them on Slack/Signal.
- **`exec` for assembly only** (ffmpeg); check `which ffmpeg` first.
