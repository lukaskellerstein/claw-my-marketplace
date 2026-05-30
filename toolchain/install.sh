#!/bin/sh
# Pod-side toolchain installer for the media + office skills in this repo.
#
# Designed for the Onion-AI exec-agent pod (read-only rootfs; all writable state
# on the PVC under ~/.openclaw). Each step is idempotent and non-fatal: a single
# transient failure must not abort the rest (mirrors base/deployment.yaml init).
#
# Required env (exported by the caller / deployment):
#   SKILLS_DIR     where the generated skills/ were copied (has package.json's to build)
#   DOCTOOLS_DIR   NODE_PATH dir for the office-gen node libs (docx/pptxgenjs/exceljs)
#   OFFICE_VENV    uv venv dir for office python (openpyxl/pandas/lxml/markitdown)
#   BIN_DIR        on PATH; must contain `uv`/`uvx` and `node`/`npm`
#   npm_config_cache, UV_* dirs   already redirected onto the PVC
# Optional flags:
#   WITH_FFMPEG=1      install a static ffmpeg into BIN_DIR (media-director assembly)
#   WITH_PLAYWRIGHT=1  install chromium for the playwright MCP / D3 + svg render QA (heavy)
set -u

log() { echo "install.sh: $*"; }

: "${SKILLS_DIR:?set SKILLS_DIR}"
: "${DOCTOOLS_DIR:?set DOCTOOLS_DIR}"
: "${OFFICE_VENV:?set OFFICE_VENV}"

# 1. Office generation node libs (the primary, always-on path: docx/pptx/xlsx
#    generation is pure JS and needs no LibreOffice). Version-guarded by marker.
DOCTOOLS_VERSION="claw-1"
if [ ! -f "$DOCTOOLS_DIR/.installed-${DOCTOOLS_VERSION}" ]; then
  mkdir -p "$DOCTOOLS_DIR"
  printf '{"name":"doctools","private":true,"dependencies":{"pptxgenjs":"4.0.1","docx":"9.7.1","exceljs":"4.4.0"}}' \
    > "$DOCTOOLS_DIR/package.json"
  if (cd "$DOCTOOLS_DIR" && npm install --no-audit --no-fund --omit=dev); then
    touch "$DOCTOOLS_DIR/.installed-${DOCTOOLS_VERSION}"
    log "office node libs installed (docx/pptxgenjs/exceljs)"
  else
    log "office node libs install failed; continuing"
  fi
fi

# 2. Per-skill node deps shipped with the skills (drawio postprocessor, svg QA).
#    The agent's skill instructions expect these prebuilt so it doesn't npm-install
#    mid-task. Find each package.json under the skills tree and build in place.
find "$SKILLS_DIR" -name package.json -not -path '*/node_modules/*' 2>/dev/null | while read -r pkg; do
  dir=$(dirname "$pkg")
  [ -d "$dir/node_modules" ] && continue
  if (cd "$dir" && npm install --no-audit --no-fund --omit=dev); then
    log "built skill deps in ${dir#$SKILLS_DIR/}"
  else
    log "skill dep build failed in ${dir#$SKILLS_DIR/}; continuing"
  fi
done

# 3. Office python (xlsx via openpyxl, data analysis via pandas, OOXML
#    unpack/pack/validate via lxml/defusedxml, images via Pillow). Installed into a
#    uv venv so the office scripts resolve their imports. soffice/LibreOffice is NOT
#    installed — the skills degrade gracefully (skip thumbnail/PDF/recalc QA).
#    markitdown is EXCLUDED: it pulls torch+onnxruntime+nvidia CUDA (~2GB) we don't
#    need; doc reading uses the lxml unpack/validate path instead.
OFFICE_PY_VERSION="claw-2"
if [ ! -f "$OFFICE_VENV/.installed-${OFFICE_PY_VERSION}" ]; then
  rm -rf "$OFFICE_VENV"
  if uv venv "$OFFICE_VENV" 2>/tmp/office-venv.log \
     && uv pip install --python "$OFFICE_VENV/bin/python" \
          openpyxl pandas lxml defusedxml Pillow 2>>/tmp/office-venv.log; then
    touch "$OFFICE_VENV/.installed-${OFFICE_PY_VERSION}"
    log "office python venv ready at $OFFICE_VENV (openpyxl/pandas/lxml/Pillow)"
  else
    log "office python venv install failed (xlsx/editing degraded); reason:"
    tail -5 /tmp/office-venv.log 2>/dev/null | sed 's/^/install.sh:   /'
  fi
fi

# 4. Optional: ffmpeg static for media-director audio/video assembly.
if [ "${WITH_FFMPEG:-0}" = "1" ] && [ -n "${BIN_DIR:-}" ] && [ ! -x "$BIN_DIR/ffmpeg" ]; then
  url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
  if curl -fsSL -o /tmp/ffmpeg.tar.xz "$url" && tar xJf /tmp/ffmpeg.tar.xz -C /tmp; then
    f=$(find /tmp -type f -name ffmpeg -path '*amd64-static*' | head -n1)
    [ -n "$f" ] && install -m 0755 "$f" "$BIN_DIR/ffmpeg" && log "ffmpeg installed"
    rm -rf /tmp/ffmpeg.tar.xz /tmp/ffmpeg-*-amd64-static
  else
    log "ffmpeg download failed; continuing (media-director assembly unavailable)"
  fi
fi

# 5. Optional: chromium for the playwright MCP and D3/SVG render QA. Heavy
#    (~150MB + system libs); enable only on pods that need rendered charts.
if [ "${WITH_PLAYWRIGHT:-0}" = "1" ]; then
  if npx --yes playwright install chromium >/dev/null 2>&1; then
    log "playwright chromium installed"
  else
    log "playwright chromium install failed; continuing (D3/svg render QA degraded)"
  fi
fi

log "done"
