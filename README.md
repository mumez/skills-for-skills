# skills-for-skills

Claude Code skills for understanding and reorganizing your other skills.

As you install more skills and plugins, it gets harder to know what each one does, which one will fire for a given prompt, and why the one you wanted didn't. This plugin adds two skills that help with that:

| Skill | What it does |
|---|---|
| [`explaining-skill`](skills/explaining-skill/SKILL.md) | Explains a skill in your own language: which prompts trigger it, what it does step by step, which files and scripts it uses, how it overlaps with skills you already have, and (for skills given by URL, or on request) a safety review. |
| [`retrospecting-skills`](skills/retrospecting-skills/SKILL.md) | Runs a skill-usage retrospective on the current session: which prompt triggered which skill, what each skill did, and which skills probably should have fired but didn't. It then asks you for a KPT (Keep / Problem / Try) and turns it into concrete fixes. |

Both skills reply in the language you write in, so you can ask in Japanese, German, or any other language.

## Installation

```
/plugin marketplace add mumez/skills-for-skills
/plugin install skills-for-skills@skills-for-skills
```

### Requirements

- Python 3.10+ (standard library only) for the bundled scripts
- `git`, if you want `explaining-skill` to fetch skills from a URL

## explaining-skill

Use it when you want to understand a skill, whether it's already installed or one you're thinking of installing.

Example prompts:

- `explain the pdf skill`
- `when does superpowers:brainstorming fire?`
- `is the xxx skill I just installed safe?`
- `is this skill worth installing? https://github.com/anthropics/skills/tree/main/skills/webapp-testing`
- `what's the difference between code-review and simplify?`

What it does:

1. Locates the skill by name among personal, project, and plugin skills (`scripts/find_skill.py`). If you give a URL, it downloads the skill into a quarantine directory under `/tmp` with git hooks, LFS, and submodules disabled (`scripts/fetch_remote.py`).
2. Reads the whole skill: frontmatter, body, references, scripts, and any plugin hooks or MCP config shipped with it. It reads the target skill's code but never runs it.
3. Compares the skill with what you already have installed to find overlaps and conflicts.
4. Writes the explanation. Short ones go straight into chat as Markdown. Long ones become an HTML report at `/tmp/YYYY-MM-DD-skill-explanation-<name>.html`, with a short summary in chat. Say "in chat" or "as HTML" to choose the format yourself.
5. For skills given by URL, it always includes a safety review, checking for risky patterns with `scripts/scan_risks.py`, and tells you whether the skill is worth installing.

It doesn't create or edit skills. Use `skill-creator` for that.

## retrospecting-skills

Use it at the end of a session to look back on how skills behaved.

Example prompts:

- `let's do a skill retrospective`
- `which skills fired this session?`
- `why didn't the commit-message skill fire?`
- `retro on skills with KPT`

It works in three phases:

1. **Facts**: `scripts/extract_skill_usage.py` reads the current session's transcript under `~/.claude/projects/`. It shows a per-prompt table of skills used and what each did, per-skill counts (slash command, model-invoked, or subagent), and a short list of skills that may have failed to fire. It also flags setup problems that hurt triggering, such as duplicate skills, missing or thin descriptions, and skills listed without a description because too many are installed.
2. **KPT**: asks you for Keep / Problem / Try and waits for your answer. If you have nothing to add, it stops there.
3. **Proposals**: gives a short summary, one recommended fix per Problem/Try, other options, side effects and conflicts, and next actions. The fixes can be prompt wording, description changes, restricting or removing conflicting skills, CLAUDE.md routing rules, or a ready-to-paste `/skill-creator` prompt for a routing skill. Long proposals are written as an HTML report in `/tmp`.

The script only reads local transcripts; it doesn't write files or send anything over the network. Changes to your skills, settings, or CLAUDE.md are only made after you choose which proposals to apply.

## License

[MIT](LICENSE)
