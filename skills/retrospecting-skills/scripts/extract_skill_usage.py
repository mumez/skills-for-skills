#!/usr/bin/env python3
"""Extract prompt -> skill usage from a Claude Code session transcript.

Usage:
  extract_skill_usage.py [--session PATH_OR_ID] [--cwd DIR] [--include-retro]

With no --session, picks the most recently modified *.jsonl in the project
directory for --cwd (default: current directory), i.e. the running session.

Prints JSON:
  session      : transcript path
  prompts      : one entry per user prompt, in order, with
                   prompt          (truncated text; slash commands shown as "/name args")
                   invocations     skills activated while handling this prompt
                                   via = "slash" | "model" | "subagent" | "read"
                   tools           tool-call counts the main agent made for this prompt
                   commands        leading words of shell commands run (e.g. "git commit": 2),
                                   to spot work done by hand that a skill could have done
                   subagents       descriptions of Agent calls (with skills they used)
                   reply_excerpt   start of the last assistant text for this prompt
  skill_counts : {skill: {"total": n, "slash": n, "model": n, "subagent": n}}  (real activations)
  skill_md_reads : {skill: n}  SKILL.md files merely read (often inspection, not usage)
  available_skills : [{name, description}] from the latest skill listing
  unused_skills    : available skill names never activated
  listing_issues   : setup problems that hurt triggering — duplicate descriptions,
                     same base name in several namespaces, near-empty descriptions,
                     personal skills also defined as a legacy command, lowercase skill.md
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

PROJECTS = os.path.expanduser("~/.claude/projects")
SELF_SKILL = "retrospecting-skills"
PROMPT_MAX = 300
REPLY_MAX = 300


def load(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return recs


def find_session(session, cwd):
    if session:
        if os.path.isfile(session):
            return session
        hits = glob.glob(os.path.join(PROJECTS, "*", session + ".jsonl"))
        if hits:
            return hits[0]
        sys.exit(f"session not found: {session}")
    proj = os.path.join(PROJECTS, re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(cwd)))
    files = glob.glob(os.path.join(proj, "*.jsonl"))
    if not files:
        files = glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
    if not files:
        sys.exit("no session transcripts found under ~/.claude/projects")
    return max(files, key=os.path.getmtime)


def trunc(s, n):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def skill_name_from_path(p):
    # .../<skill-name>/SKILL.md
    return os.path.basename(os.path.dirname(p))


SKILL_MD_RE = re.compile(r"(\S*/([A-Za-z0-9][\w.-]*)/(?:SKILL|skill)\.md)")


def skill_md_reads(cmd):
    """Skill names whose SKILL.md is printed by cat/head/sed... (not ls/find/grep)."""
    out = []
    for seg in SEGMENT_RE.split(cmd):
        words = seg.split()
        if words and words[0].split("/")[-1] in SKILL_READERS:
            out += [m.group(2) for m in SKILL_MD_RE.finditer(seg)]
    return out
# Read-only / plumbing commands that say nothing about skill-worthy work.
NOISE_CMDS = {"cd", "echo", "true", "false", "sleep", "export", "set", "source", ".", "cat", "head", "tail",
              "sed", "awk", "grep", "rg", "find", "ls", "wc", "sort", "uniq", "cut", "tr", "jq", "xargs",
              "for", "do", "done", "if", "then", "fi", "while", "test", "[", "which", "command", "printf",
              "pwd", "date", "break", "continue", "exit", "return", "local", "else", "elif", "basename", "dirname", "tee", "diff", "stat", "file", "less", "realpath", "mkdir"}
SKILL_READERS = {"cat", "head", "less", "bat", "sed", "nl"}
SEGMENT_RE = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")


def command_heads(cmd):
    """'cd x && git commit -m ..' -> ['git commit']; skips cd/echo-like noise."""
    heads = []
    for seg in SEGMENT_RE.split(cmd.strip().splitlines()[0] if cmd.strip() else ""):
        words = [w for w in seg.split() if not re.match(r"^\w+=", w)]
        if not words or not re.match(r"^[a-z][\w./-]*$", words[0].split("/")[-1]) or words[0].split("/")[-1] in NOISE_CMDS:
            continue
        sub = words[1] if len(words) > 1 and re.match(r"^[a-z][\w-]*$", words[1]) else ""
        heads.append((words[0].split("/")[-1] + " " + sub).strip())
    return heads


def listing_issues(listing):
    home = os.path.expanduser("~/.claude")
    issues = []
    by_desc = collections.defaultdict(list)
    by_base = collections.defaultdict(list)
    for s in listing:
        if s["description"]:
            by_desc[s["description"]].append(s["name"])
        by_base[s["name"].split(":")[-1]].append(s["name"])
    for desc, names in by_desc.items():
        if len(names) > 1:
            issues.append({"kind": "duplicate_description", "skills": names})
    for base, names in by_base.items():
        if len(names) > 1:
            issues.append({"kind": "same_base_name", "skills": names})
    for s in listing:
        name = s["name"]
        if not s["description"]:
            # Claude Code drops descriptions when the listing exceeds its budget (too many skills).
            issues.append({"kind": "listed_without_description", "skills": [name]})
        elif len(s["description"]) < 40:
            issues.append({"kind": "thin_description", "skills": [name], "description": s["description"]})
        if ":" in name:
            continue
        skill_dir = os.path.join(home, "skills", name)
        cmd = os.path.join(home, "commands", name + ".md")
        if os.path.isdir(skill_dir) and os.path.exists(cmd):
            issues.append({"kind": "also_legacy_command", "skills": [name], "paths": [skill_dir, cmd]})
        if os.path.exists(os.path.join(skill_dir, "skill.md")) and not os.path.exists(os.path.join(skill_dir, "SKILL.md")):
            issues.append({"kind": "lowercase_skill_md", "skills": [name], "paths": [os.path.join(skill_dir, "skill.md")]})
    bare = [i["skills"][0] for i in issues if i["kind"] == "listed_without_description"]
    issues = [i for i in issues if i["kind"] != "listed_without_description"]
    if bare:
        issues.append({"kind": "listed_without_description", "count": len(bare), "of": len(listing), "skills": bare})
    return issues


COMMAND_RE = re.compile(r"<command-name>/?([^<]+)</command-name>")
ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)
# Harness-generated user records that are not new human prompts.
CONTINUATION_PREFIXES = ("<task-notification>", "<system-reminder>")
NOISE_PREFIXES = ("<local-command-stdout>", "<local-command-stderr>", "<bash-stdout>",
                  "<bash-stderr>", "Caveat:", "[Request interrupted")


def user_text(rec):
    """Return the human-typed text of a user record, or None if it isn't a prompt."""
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isCompactSummary"):
        return None
    if rec.get("isSidechain"):
        return None
    c = rec.get("message", {}).get("content")
    if isinstance(c, str):
        text = c
    elif isinstance(c, list):
        if any(x.get("type") == "tool_result" for x in c if isinstance(x, dict)):
            return None
        text = "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    else:
        return None
    text = text.strip()
    if not text or text.startswith(NOISE_PREFIXES):
        return None
    return text


def parse_listing(recs):
    """Merge skill_listing attachments: an initial listing, then deltas that add skills."""
    skills = {}
    for r in recs:
        a = r.get("attachment")
        if not (isinstance(a, dict) and a.get("type") == "skill_listing" and a.get("content")):
            continue
        if a.get("isInitial"):
            skills = {}
        for line in a["content"].splitlines():
            m = re.match(r"^- ([^:\s]+(?::[^:\s]+)?)(?::\s*(.*))?$", line)
            if m:
                skills[m.group(1)] = {"name": m.group(1), "description": trunc(m.group(2) or "", 160)}
    return list(skills.values())


def subagent_usage(session_path):
    """Map Agent toolUseId -> list of (skill, via) used inside that subagent (recursively flat)."""
    base = os.path.splitext(session_path)[0]
    out = {}
    for meta_path in glob.glob(os.path.join(base, "subagents", "*.meta.json")):
        try:
            meta = json.load(open(meta_path, encoding="utf-8"))
        except Exception:
            continue
        jl = meta_path[: -len(".meta.json")] + ".jsonl"
        if not os.path.exists(jl):
            continue
        used = []
        for r in load(jl):
            c = r.get("message", {}).get("content") if isinstance(r.get("message"), dict) else None
            if not isinstance(c, list):
                continue
            for x in c:
                if not isinstance(x, dict) or x.get("type") != "tool_use":
                    continue
                inp = x.get("input") or {}
                if x.get("name") == "Skill" and inp.get("skill"):
                    used.append((inp["skill"], "subagent"))
                elif x.get("name") == "Read" and str(inp.get("file_path", "")).lower().endswith("skill.md"):
                    used.append((skill_name_from_path(inp["file_path"]), "read"))
                elif x.get("name") == "Bash":
                    for name in skill_md_reads(str(inp.get("command", ""))):
                        used.append((name, "read"))
        out[meta.get("toolUseId")] = {"description": meta.get("description", ""), "used": used}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--include-retro", action="store_true",
                    help="keep the prompt that invoked retrospecting-skills itself")
    args = ap.parse_args()

    path = find_session(args.session, args.cwd)
    recs = load(path)
    listing = parse_listing(recs)
    listed = {s["name"] for s in listing}
    subs = subagent_usage(path)

    prompts = []
    cur = None
    pending_slash = None  # slash command waiting for confirmation that it was a skill

    for r in recs:
        text = user_text(r)
        if text is not None and text.startswith(CONTINUATION_PREFIXES):
            if cur is not None:
                cur["notifications"] = cur.get("notifications", 0) + 1
            continue
        if text is not None:
            m = COMMAND_RE.search(text)
            if m:
                name = m.group(1).strip()
                am = ARGS_RE.search(text)
                shown = "/" + name + ((" " + am.group(1).strip()) if am and am.group(1).strip() else "")
            else:
                name, shown = None, text
            cur = {"index": len(prompts) + 1, "timestamp": r.get("timestamp"),
                   "prompt": trunc(shown, PROMPT_MAX), "invocations": [],
                   "tools": collections.Counter(), "commands": collections.Counter(), "subagents": [], "reply_excerpt": ""}
            prompts.append(cur)
            pending_slash = name
            if name and name in listed:
                cur["invocations"].append({"skill": name, "via": "slash"})
                pending_slash = None
            continue

        if cur is None:
            continue

        # A slash command for a skill is followed by an isMeta record carrying the skill body.
        if pending_slash and r.get("type") == "user" and r.get("isMeta"):
            c = r.get("message", {}).get("content")
            body = c if isinstance(c, str) else " ".join(
                x.get("text", "") for x in (c or []) if isinstance(x, dict))
            if "Base directory for this skill" in body or body.lstrip().startswith("#"):
                cur["invocations"].append({"skill": pending_slash, "via": "slash"})
            pending_slash = None
            continue

        msg = r.get("message")
        if r.get("type") != "assistant" or not isinstance(msg, dict) or r.get("isSidechain"):
            continue
        for x in msg.get("content") or []:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "text" and x.get("text", "").strip():
                cur["reply_excerpt"] = trunc(x["text"], REPLY_MAX)
            if x.get("type") != "tool_use":
                continue
            name, inp = x.get("name"), x.get("input") or {}
            cur["tools"][name] += 1
            if name == "Skill" and inp.get("skill"):
                inv = {"skill": inp["skill"], "via": "model"}
                if inp.get("args"):
                    inv["args"] = trunc(str(inp["args"]), 120)
                cur["invocations"].append(inv)
            elif name == "Read" and str(inp.get("file_path", "")).lower().endswith("skill.md"):
                cur["invocations"].append({"skill": skill_name_from_path(inp["file_path"]), "via": "read"})
            elif name == "Bash":
                cmd = str(inp.get("command", ""))
                for h in command_heads(cmd):
                    cur["commands"][h] += 1
                for name in skill_md_reads(cmd):
                    cur["invocations"].append({"skill": name, "via": "read"})
            elif name in ("Agent", "Task"):
                sa = subs.get(x.get("id"), {})
                entry = {"description": inp.get("description") or sa.get("description", ""),
                         "subagent_type": inp.get("subagent_type", "general-purpose"),
                         "skills": sorted({s for s, _ in sa.get("used", [])})}
                cur["subagents"].append(entry)
                for s, via in sa.get("used", []):
                    cur["invocations"].append({"skill": s, "via": via, "in_subagent": entry["description"]})

    # Drop the retrospective itself (and anything after it) unless asked not to.
    if not args.include_retro:
        for i in range(len(prompts) - 1, -1, -1):
            if any(SELF_SKILL in inv["skill"] for inv in prompts[i]["invocations"]):
                prompts = prompts[:i]
                break

    counts = collections.defaultdict(lambda: collections.Counter())
    reads = collections.Counter()
    known = {x["name"].split(":")[-1] for x in listing}
    for p in prompts:
        p["tools"] = dict(p["tools"].most_common())
        p["commands"] = dict(p["commands"].most_common(8))
        for inv in p["invocations"]:
            if inv["via"] == "read":
                if inv["skill"] in known:
                    reads[inv["skill"]] += 1
                continue
            counts[inv["skill"]][inv["via"]] += 1
            counts[inv["skill"]]["total"] += 1

    used_bases = {k.split(":")[-1] for k in counts} | set(counts)
    result = {
        "session": path,
        "prompt_count": len(prompts),
        "prompts": prompts,
        "skill_counts": {k: dict(v) for k, v in sorted(counts.items(), key=lambda kv: -kv[1]["total"])},
        "skill_md_reads": dict(reads.most_common()),
        "available_skills": listing,
        "unused_skills": [s["name"] for s in listing
                          if s["name"] not in used_bases and s["name"].split(":")[-1] not in used_bases],
        "listing_issues": listing_issues(listing),
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
