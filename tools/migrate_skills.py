#!/usr/bin/env python3
"""Generate OpenClaw-compatible skills/ from a codex-my-marketplace checkout.

Why this exists: the skill *prose* is single-source in codex-my-marketplace
(Claude/Codex format). OpenClaw's skill loader needs three mechanical changes,
applied here deterministically so we never hand-fork 50+ SKILL.md files:

  1. Frontmatter must be single-line keys (OpenClaw's embedded parser does not
     read YAML block/folded scalars or multi-line `metadata`). We collapse
     `name` and `description` to one line and emit `metadata` as single-line
     JSON carrying the per-skill `metadata.openclaw` gating from the manifest.
  2. `${CLAUDE_PLUGIN_ROOT}/skills/` references are rewritten to `{baseDir}/../`.
     In the pod every skill lands as a flat sibling under one extraDirs root, so
     `{baseDir}/../<other-skill>/...` resolves for both self- and cross-skill
     references. `{baseDir}` is OpenClaw's skill-folder placeholder.
  3. The skill directory is copied verbatim otherwise (references/, scripts/).

Usage:
  python3 tools/migrate_skills.py [--source DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path.home() / "Projects/Github/lukaskellerstein/codex-my-marketplace"

# Skills land as flat siblings under one extraDirs root, so a plugin-root skills
# reference becomes `{baseDir}/../`. Any other plugin-root reference (e.g. the
# office `scripts/office/*` shared tree) is redirected into the `_office-shared`
# sibling dir we copy alongside the skills (a dir with no SKILL.md is ignored by
# the skill scanner, so it is safe to colocate shared assets there).
PLUGIN_ROOT_SKILLS_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/skills/")
PLUGIN_ROOT_OTHER_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/")


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_frontmatter(md: str) -> tuple[str, str]:
    """Return (frontmatter_body, rest) for a `---`-delimited frontmatter block."""
    if not md.startswith("---"):
        raise ValueError("SKILL.md has no frontmatter")
    end = md.index("\n---", 3)
    fm = md[3:end].lstrip("\n")
    rest = md[end + len("\n---"):]
    rest = rest[1:] if rest.startswith("\n") else rest
    return fm, rest


def parse_scalar(fm: str, key: str) -> str:
    """Extract a scalar frontmatter value (plain, quoted, or `>`/`|` block)."""
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        m = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
        if not m:
            continue
        first = m.group(1).strip()
        if first in (">", "|", ">-", "|-", ">+", "|+"):
            block: list[str] = []
            for follow in lines[i + 1:]:
                if follow.strip() == "" or follow.startswith((" ", "\t")):
                    block.append(follow.strip())
                else:
                    break
            return collapse_ws(" ".join(block))
        if (first.startswith('"') and first.endswith('"')) or (
            first.startswith("'") and first.endswith("'")
        ):
            first = first[1:-1]
        return collapse_ws(first)
    raise ValueError(f"frontmatter key not found: {key}")


def yaml_dq(value: str) -> str:
    """YAML double-quoted scalar."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def rewrite_paths(text: str) -> str:
    text = PLUGIN_ROOT_SKILLS_RE.sub("{baseDir}/../", text)
    return PLUGIN_ROOT_OTHER_RE.sub("{baseDir}/../_office-shared/", text)


def build_frontmatter(name: str, description: str, gating: dict) -> str:
    lines = [f"name: {name}", f"description: {yaml_dq(description)}"]
    if gating:
        meta = json.dumps({"openclaw": gating}, separators=(", ", ": "))
        lines.append(f"metadata: {meta}")
    return "---\n" + "\n".join(lines) + "\n---\n"


def migrate_skill(entry: dict, source: Path, out: Path) -> str:
    name = entry["name"]
    src_dir = source / entry["sourcePath"]
    if not (src_dir / "SKILL.md").is_file():
        raise FileNotFoundError(f"missing SKILL.md: {src_dir}")

    dst_dir = out / name
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)

    skill_md = (src_dir / "SKILL.md").read_text(encoding="utf-8")
    fm, body = split_frontmatter(skill_md)
    new_md = build_frontmatter(
        parse_scalar(fm, "name") if "name:" in fm else name,
        parse_scalar(fm, "description"),
        entry.get("gating") or {},
    ) + rewrite_paths(body)
    (dst_dir / "SKILL.md").write_text(new_md, encoding="utf-8")

    # Rewrite path placeholders in every other markdown reference too.
    for md_file in dst_dir.rglob("*.md"):
        if md_file.name == "SKILL.md":
            continue
        original = md_file.read_text(encoding="utf-8")
        rewritten = rewrite_paths(original)
        if rewritten != original:
            md_file.write_text(rewritten, encoding="utf-8")
    return name


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "skills")
    args = ap.parse_args()

    if not args.source.is_dir():
        raise SystemExit(f"source checkout not found: {args.source}")

    manifest = json.loads((REPO_ROOT / "skills.manifest.json").read_text("utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)

    for asset in manifest.get("sharedAssets", []):
        src = args.source / asset["sourcePath"]
        dst = args.out / asset["dest"]
        if not src.is_dir():
            raise FileNotFoundError(f"missing shared asset: {src}")
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"shared asset: {asset['sourcePath']} -> {asset['dest']}")

    done = [migrate_skill(e, args.source, args.out) for e in manifest["skills"]]
    print(f"migrated {len(done)} skills -> {args.out}")
    for n in done:
        print(f"  - {n}")


if __name__ == "__main__":
    main()
