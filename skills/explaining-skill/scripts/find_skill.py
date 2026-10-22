#!/usr/bin/env python3
"""Locate installed Claude Code skills by name.

Usage:
  find_skill.py <query> [--cwd DIR]   # exact match on name / plugin:name, then fuzzy
  find_skill.py --list [--brief] [--cwd DIR]  # list every installed skill
                                       # (--brief: name/description/enabled only,
                                       #  handy for comparing overlap)
  find_skill.py --similar "<text>" [--cwd DIR]  # top 15 installed skills whose
                                       # name+description share the most words
                                       # with <text> (e.g. the target's description)

Searches personal skills (~/.claude/skills), synced claude.ai skills
(anthropic-skills:*), project skills (<cwd>/.claude/skills and parents), and
skills bundled in installed plugins (using the active installPath from
~/.claude/plugins/installed_plugins.json, so stale cached versions are ignored).
Prints JSON: a list of {qualified_name, name, source, skill_dir, description,
enabled, scope}. For plugins, `enabled` comes from enabledPlugins in the user
settings, or in the project settings for local/project-scoped installs.
"""
import json
import os
import re
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE = HOME / ".claude"


def frontmatter(skill_md: Path) -> dict:
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    data, key = {}, None
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if km:
            key, val = km.group(1), km.group(2).strip()
            data[key] = val.strip("'\"") if val not in ("|", ">", "|-", ">-") else ""
        elif key and line.startswith((" ", "\t")):
            data[key] = (data[key] + " " + line.strip()).strip()
    return data


def skill_file(d: Path) -> Path | None:
    """SKILL.md in d, matched case-insensitively (some skills ship skill.md)."""
    if not d.is_dir():
        return None
    for f in d.iterdir():
        if f.name.lower() == "skill.md" and f.is_file():
            return f
    return None


def all_skill_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.name.lower() == "skill.md"
                  and p.is_file() and "node_modules" not in p.parts)


def enabled_plugins(settings_dir: Path) -> dict:
    merged = {}
    for name in ("settings.json", "settings.local.json"):
        f = settings_dir / name
        try:
            merged.update(json.loads(f.read_text()).get("enabledPlugins", {}) or {})
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    return merged


def entry(skill_md: Path, prefix: str | None, source: str, enabled=True, scope="user") -> dict:
    fm = frontmatter(skill_md)
    name = fm.get("name") or skill_md.parent.name
    return {
        "qualified_name": f"{prefix}:{name}" if prefix else name,
        "name": name,
        "dir_name": skill_md.parent.name,
        "source": source,
        "skill_dir": str(skill_md.parent),
        "description": fm.get("description", "")[:300],
        "enabled": enabled,
        "scope": scope,
    }


def collect(cwd: Path) -> list[dict]:
    found = []
    personal = CLAUDE / "skills"
    if personal.is_dir():
        for d in sorted(personal.iterdir()):
            f = skill_file(d)
            if f:
                found.append(entry(f, None, "personal"))
        synced = personal / "synced"
        if synced.is_dir():
            for md in [f for d in sorted(synced.glob("*/*")) if (f := skill_file(d))]:
                found.append(entry(md, "anthropic-skills", "synced (claude.ai)"))

    seen_proj = set()
    for p in [cwd, *cwd.parents]:
        sk = p / ".claude" / "skills"
        if sk.is_dir() and sk.resolve() != personal.resolve() and sk not in seen_proj:
            seen_proj.add(sk)
            for md in [f for d in sorted(sk.iterdir()) if (f := skill_file(d))]:
                found.append(entry(md, None, f"project ({p})", True, f"project {p}"))

    reg = CLAUDE / "plugins" / "installed_plugins.json"
    if reg.is_file():
        try:
            plugins = json.loads(reg.read_text()).get("plugins", {})
        except (OSError, json.JSONDecodeError):
            plugins = {}
        user_enabled = enabled_plugins(CLAUDE)
        for key, installs in plugins.items():
            plugin = key.split("@")[0]
            for inst in installs:
                root = Path(inst.get("installPath", ""))
                scope = inst.get("scope", "user")
                proj = inst.get("projectPath")
                if proj:
                    on = enabled_plugins(Path(proj) / ".claude").get(key, scope in ("local", "project"))
                    scope = f"{scope} {proj}"
                else:
                    on = user_enabled.get(key, False)
                if not root.is_dir():
                    continue
                for md in all_skill_files(root):
                    found.append(entry(md, plugin, f"plugin {key} v{inst.get('version', '?')}", on, scope))
    return found


STOP = set("the a an and or of to for in on with when use this that is are be it as by any user skill skills you your from into".split())


def tokens(text: str) -> set:
    text = text.lower()
    words = {w for w in re.findall(r"[a-z][a-z0-9-]{2,}", text) if w not in STOP}
    cjk = re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]+", text)
    words |= {c[i:i + 2] for c in cjk for i in range(len(c) - 1)}
    return words


def main() -> None:
    args = sys.argv[1:]
    cwd = Path(os.getcwd())
    if "--cwd" in args:
        i = args.index("--cwd")
        cwd = Path(args[i + 1]).expanduser().resolve()
        del args[i : i + 2]
    skills = collect(cwd)
    if args and args[0] == "--similar":
        target = tokens(" ".join(args[1:]))
        scored, seen = [], set()
        for sk in skills:
            if sk["qualified_name"] in seen:
                continue
            seen.add(sk["qualified_name"])
            t = tokens(sk["qualified_name"] + " " + sk["description"])
            common = target & t
            if common:
                scored.append((len(common) / (len(t) ** 0.5 + 1), sk, sorted(common)))
        scored.sort(key=lambda x: -x[0])
        print(json.dumps([{"qualified_name": sk["qualified_name"], "enabled": sk["enabled"],
                           "shared_terms": common[:12], "description": sk["description"]}
                          for _, sk, common in scored[:15]], ensure_ascii=False, indent=1))
        return
    if not args or args[0] == "--list":
        if "--brief" in args:
            skills = [{k: s[k] for k in ("qualified_name", "description", "enabled")} for s in skills]
        print(json.dumps(skills, ensure_ascii=False, indent=1))
        return

    q = args[0].strip().lstrip("/").lower()
    def keys(s):
        return {s["qualified_name"].lower(), s["name"].lower(), s["dir_name"].lower()}
    exact = [s for s in skills if q in keys(s)]
    if exact:
        result = {"match": "exact", "candidates": exact}
    else:
        bare = q.split(":")[-1]
        fuzzy = [s for s in skills if any(bare in k for k in keys(s))]
        result = {"match": "fuzzy" if fuzzy else "none", "candidates": fuzzy}
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
