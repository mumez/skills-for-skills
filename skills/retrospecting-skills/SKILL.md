---
name: retrospecting-skills
description: Runs a skill-usage retrospective on the current Claude Code session — lists which prompt triggered which skill (slash, model-invoked, or inside subagents), what each skill actually did, and how many times; flags prompts where an installed skill probably should have fired but didn't; then asks the user for a KPT (Keep / Problem / Try) and turns it into concrete fixes (prompt phrasing, description tweaks, removing conflicting skills, a routing "playbook" skill with a ready-to-paste skill-creator prompt). Use this whenever a session is wrapping up and the user wants to look back on skill behaviour, e.g. "let's do a skill retrospective", "which skills were used in today's session?", "retro on skills with KPT", "why didn't the xxx skill fire?", "which skills fired this session?", "skill usage review". Requests often come in other languages (Japanese, etc.) — trigger on the intent, not the English wording. Also use when the user complains that a skill didn't trigger, triggered wrongly, or two skills conflicted during the session.
---

# Retrospecting skills

The goal is to help the user tune their skill setup from real evidence: what they typed, which skills actually activated, and what those skills did. The flow has three phases: **facts → user's KPT → improvement proposals**. Keep the phases separate. If you offer opinions while showing the facts, the user's own KPT gets anchored to yours.

Talk to the user in the language they've been using in the session. The section names, table headers, labels and examples in this skill are written in English; translate them into the user's language when you present them (a Japanese session gets Japanese headings and column names). Keep identifiers (skill names, tool names, commands, JSON keys, file paths) as-is.

## Phase 1: Collect and show the facts

Run the bundled extractor. With no arguments it picks the running session for the current working directory:

```bash
python3 <this-skill-dir>/scripts/extract_skill_usage.py            # current session
python3 <this-skill-dir>/scripts/extract_skill_usage.py --session <id-or-path>   # a specific one
```

It prints JSON with `prompts` (each with `invocations`, `tools`, `commands`, `subagents`, `reply_excerpt`), `skill_counts` (real activations), `skill_md_reads`, `available_skills`, `unused_skills` and `listing_issues`. The prompt that invoked this retrospective is already excluded. If the script finds nothing (for example the transcript is missing), say so and fall back to your own memory of the conversation, flagging that counts may be incomplete.

How to read `invocations[].via`:
- `slash`: the user typed `/skill-name`. This is explicit, so it isn't evidence about triggering quality.
- `model`: you (the agent) chose to call the Skill tool. This is the real triggering signal.
- `subagent`: a subagent called the Skill tool.
- `read`: someone read a `SKILL.md` file. This is often *not* usage. An agent may have been inspecting, explaining or evaluating that skill. Use the prompt and subagent description to decide, and label it honestly (e.g. "read only (inspected as the subject of an explanation)").

`commands` lists the shell commands run for each prompt, such as `git commit` or `gh pr`. Use it to spot work done by hand that a skill exists for. For example, the user asked "commit this" and `git commit` ran, but `commit-message` never fired.

`listing_issues` lists setup problems that hurt triggering whatever the prompt says. Check it every time, because these are often the root cause behind a "didn't fire":
- `listed_without_description`: when too many skills are installed, Claude Code drops descriptions from the listing it shows the agent, so these skills appear as a bare name. The agent can barely tell when to use them. If a skill the user wanted is on this list, that alone explains a lot.
- `duplicate_description` / `same_base_name`: the same skill installed twice (e.g. from two plugins), or two skills sharing a name. These compete with each other.
- `thin_description`: the description is only a title (e.g. "Commit Message Generator"), with no "use when…".
- `also_legacy_command` / `lowercase_skill_md`: a personal skill that is also defined in `~/.claude/commands/`, or whose file is `skill.md` rather than `SKILL.md`. Either can make the wrong definition load, or none at all.

To describe **what each skill actually did** (its "effect"), combine the `tools` counts, the subagent descriptions, the `reply_excerpt`, and your own memory of the session. Be concrete, e.g. "read git diff, generated an English commit message and committed", not "used the commit-message skill".

Present it in chat as Markdown:

1. **Per-prompt table**: `# | Prompt (summary) | Skills used (route) | What it actually did`. Summarise long or pasted prompts in one line. Include prompts where no skill fired too, because those are where missed triggers hide. If there are many trivial no-skill prompts in a row (e.g. "ok", "continue"), collapse them into one row.
2. **Per-skill counts**: `Skill | Count | Breakdown (slash/model/subagent)` from `skill_counts`. If `skill_md_reads` is non-empty, add one line below the table listing them as read only, with what they were read for if you can tell.
3. **Skills that may have failed to fire**: compare each prompt with `available_skills` and list the plausible misses. For each, name the prompt number, the skill, and one line of reasoning based on the description. These are hypotheses, so present them that way, and keep the list short (only ones you'd actually bet on). A skill the user deliberately avoided is not a miss. Also note it briefly if a skill fired that probably shouldn't have. If `listing_issues` explains a miss, say so here in one line (e.g. "it was listed without a description").

Keep the commentary to what helps read the table. Save the evaluation for Phase 3.

## Phase 2: Ask for the KPT

Ask the user for their KPT in a single plain chat message (not a multiple-choice tool, since these are free-form thoughts). Any item can be left blank. Offer a template they can fill in (translate the hints in parentheses; keep the Keep / Problem / Try labels):

```
Keep:    (what worked as you expected)
Problem: (a skill you wanted didn't fire, an unwanted skill ran, etc.)
Try:     (ideas for what you'd like to happen next time)
```

Mention that your "may have failed to fire" list can be used as raw material for Problem, but that only the user knows what they actually expected. Then stop and wait for their answer.

**If every item comes back empty** (or the user says "nothing", "no", "skip", or the equivalent in their language), end the session there with a one-line closing. Don't push proposals they didn't ask for.

## Phase 3: Propose concrete improvements

Respond to each Problem and Try the user gave, and treat each Keep as something to protect. Every proposal should point to evidence (prompt #, skill name, a phrase from a description, a `listing_issues` entry) and be actionable today. If a KPT item (Keep, Problem or Try) has no direct evidence in this session — it refers to other sessions or general experience, or the only in-session trace is a slash invocation or a `read`, which say nothing about automatic triggering — say so in one line, take the user's account as the main evidence, and support it with what you can check now: indirect traces in the session (e.g. test commands in `commands`, `reply_excerpt`), the relevant skills' descriptions, `available_skills`, and `listing_issues`. Read `references/improvement-playbook.md` for the toolbox: prompt phrasing, description tuning, fixing setup issues, restricting or removing conflicting skills, CLAUDE.md routing rules, and a routing playbook skill (with a ready-to-paste `/skill-creator` prompt).

### Structure: lead with the gist, then one recommendation, then alternatives

A long list of equally weighted options is hard to take in. Users want to know what to do first. Use this order:

1. **In a nutshell** (summary advice): 2–4 lines of plain advice covering the whole retrospective, e.g. "commit-message is rarely picked because of a setup problem. Fix its SKILL.md first, then keep only one planning skill". Someone who reads only this should know what to do.
2. **Recommended fixes**: for each Problem/Try, give the *one* fix you'd actually pick, with the reasoning and evidence, plus anything they can paste (frontmatter, CLAUDE.md lines, a `/skill-creator` prompt) in a code block.
3. **Other options**: other viable fixes, one or two lines each, with when you'd prefer them instead. Keep them brief, since they are there for reference.
4. **Side effects and conflicts**: look across all the proposals and the installed skills. What else changes if they apply these? Will a broadened description start firing on prompts where it shouldn't? Is there an overlapping skill (another plugin's version, a meta-skill, a CLAUDE.md rule) that will now compete, or that should be given a separate role? Does anything trade off against a Keep? Users find this cross-cutting check valuable, because raising one skill's trigger rate can quietly change the behaviour of others.
5. **Summary and next actions**: a short numbered list of what to do next, in order. End by asking which ones they'd like you to apply. Editing skills, settings, or CLAUDE.md changes the user's environment, so do it only after they choose.

Omit any of sections 2–5 that would be empty, heading included; don't write "none" under a heading. In a nutshell is always there. When nothing remains to apply (e.g. only Keeps came back), put the Keep-related notes in In a nutshell, drop the apply question, and close with one line.

### Where to put it: HTML when it's long

The proposals usually run longer than a screen. Proposals that size are hard to read in a terminal, so when they'd exceed roughly 40 lines of Markdown, write them as an HTML report and keep the chat reply short. Otherwise reply in chat. An explicit request ("in chat" / "as HTML", in any language) wins either way.

1. Copy `<this-skill-dir>/assets/report.html` to `/tmp/YYYY-MM-DD-skill-retro-<short-session-id>.html` and set `__LANG__` and `__TITLE__`.
2. Replace the `<!-- CONTENT ... -->` comment with real HTML (no Markdown syntax): `<h1>`, `<p class="meta">` (session, date, prompt count), `<div class="tldr">` holding the In a nutshell lines (the box is that section; don't give it an `<h2>`), then one `<h2>` for each remaining section, in order. For reference, repeat the Phase 1 tables and the user's KPT inside a `<details>` near the top. Building blocks: `<div class="rec">` around each recommended fix, `<p class="alt">` or a list for alternatives, `<div class="callout warn">` for side-effect warnings, and `<pre><code>` for pasteable text (the page adds a Copy button to every code block). Escape `<`, `>`, `&` in code and quoted text.
3. Try to open it with `wslview`, then `xdg-open`, then `open` (check with `command -v` first, run in the background, discard output). Don't fail if none works.
4. In chat, give the report path, the In a nutshell lines, and the Summary and next actions list. Don't repeat the whole report.
