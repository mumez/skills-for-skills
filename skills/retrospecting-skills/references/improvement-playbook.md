# Improvement playbook

A toolbox for Phase 3. Pick what fits the user's Problem/Try. Don't use every item.

## 1. How skill triggering works (for explaining "why it didn't fire")

- The agent sees only each skill's `name` + `description` in the skill listing, and decides from that alone whether to call the Skill tool. The SKILL.md body is invisible until the skill is loaded.
- Agents tend to skip skills for tasks they think they can do directly (simple, one-step requests). A short prompt like "commit this" may be handled with plain `git` even when a commit skill exists.
- Many installed skills with similar descriptions dilute each other. The agent picks one, or neither.
- **Listing budget**: when many skills are installed, Claude Code shortens or drops descriptions in the listing it shows the agent. `listing_issues.listed_without_description` reveals which skills appeared as a bare name. The fix for these is usually to *reduce the number of installed skills* (disable unused plugins), not to edit the description, because the description wasn't shown at all.
- Strongly worded always-on instructions (e.g. a "use a skill before anything" meta-skill or CLAUDE.md rules) can pull triggering toward particular skills.

## 2. Prompt-side fixes (zero setup)

- Use words that appear in the target skill's description, since triggering matches on them. Quote the description phrase in your suggestion.
- Name the skill outright: "use the xxx skill to …", or type `/xxx`, which always loads it.
- Split compound requests when one part needs a skill that tends to get skipped. Or list the steps explicitly ("commit with the commit-message skill, then open the PR with the pr skill").

## 3. Description-side fixes

- Add the user's actual phrasings (from the session table) as trigger examples in the description, including non-English wording if that's how they write.
- Add "Use this whenever …, even if the user doesn't say X" for undertriggering. Add "Not for …; use yyy instead" for overtriggering and conflicts.
- For systematic tuning, suggest skill-creator's description optimization: `/skill-creator optimize the description of <skill-name>`. It builds should/shouldn't-trigger eval queries and iterates.

## 3b. Setup fixes (from `listing_issues`)

- **thin_description**: write a real description: what it does, plus "Use whenever …" with the user's actual phrasings. Without a description, the listing shows only the first heading.
- **lowercase_skill_md**: rename `skill.md` → `SKILL.md`. Some loaders only pick up the exact name, and a lowercase file may load partially or as something else.
- **also_legacy_command**: the same thing is defined in `~/.claude/commands/<name>.md` and `~/.claude/skills/<name>/`. Pick one (usually the skill) and move the other aside. Otherwise the run may load the command body, which has no trigger description.
- **duplicate_description / same_base_name**: the same skill installed twice (e.g. `skill-creator` from two sources), or two different skills sharing a name (`pr` vs `mattpocock-skills:pr`). Keep one, or make the descriptions clearly distinct ("Not for …; use X instead").

## 4. Conflicts and noise: restricting or removing skills

Suggest the lightest option first, and say it's a suggestion. Apply only on request.

- **Make a skill manual-only**: add `disable-model-invocation: true` to its SKILL.md frontmatter. It then runs only via `/name`, and stops competing for automatic triggering.
- **Block a skill**: add a permission deny rule for the Skill tool, e.g. `"permissions": {"deny": ["Skill(skill-name)"]}` in `~/.claude/settings.json` or the project settings.
- **Plugin skills**: disable the whole plugin via `/plugin` (or `enabledPlugins` in settings) if most of its skills are unused noise.
- **Personal skills** (`~/.claude/skills/<name>`): move the directory out (e.g. to `~/.claude/skills-disabled/`). This is reversible, unlike deleting.
- If unsure that a setting key is still current, say so and suggest checking the Claude Code docs (or the `update-config` skill) rather than asserting it.

`unused_skills` from the extractor helps here, but one session is a small sample. Phrase removal advice as "unused in this session; if you don't use it in other sessions either, …".

## 5. Routing playbook skill

Use this when the user's problem is "the right skill depends on the situation" (e.g. several review skills, several TDD skills from different plugins, a project-specific vs. a generic workflow). A playbook skill has a broad description that triggers on the whole task family, and its body is a routing table that tells the agent which specialised skill to invoke for which situation.

Give the user a ready-to-paste prompt for skill-creator, filled in with the concrete skills and situations from the session. Write it in the user's language (translate the template). Template:

```
/skill-creator I want to create a routing skill called <playbook-name>.

Purpose: when a request in <task area> comes in, route it to the right skill for the situation.

Routing rules:
- <situation A (e.g. editing Pharo/Tonel code)> → use <skill-x>
- <situation B (e.g. general bug investigation)> → use <skill-y>
- <situation C> → <skill-z>, but not when <condition>

Prompts that should trigger it: "<actual prompt 1 from the session>", "<actual prompt 2>"
Prompts that should not: "<near-miss example>"

Competing existing skills: <skill-y> and <skill-w> (their descriptions overlap)
This skill does no work itself; it only invokes the matching skill with the Skill tool.
```

Alternative: if there are only 1–2 rules, a CLAUDE.md snippet is lighter:

```markdown
## Skill routing
- Smalltalk/Tonel code changes → use smalltalk-dev:smalltalk-developer first
- Commits → commit-message, PR creation → pr (not raw git commands)
```

## 6. Side-effect check (for the Side effects and conflicts section)

Before finalising, walk through every proposal with these questions:
- **Overtriggering**: if a description gets broader ("use EVERY time …"), which near-miss prompts from this session would it now fire on? Name one or two.
- **Competing skills**: is there another installed skill (other plugin, same base name, a meta-skill like using-superpowers, or a CLAUDE.md rule) covering the same ground? Say how the roles should split, e.g. "pr-review-response for the procedure, superpowers:receiving-code-review for the mindset". Or say which one to restrict.
- **Chains**: does the fix break or bypass a chain that currently works (e.g. `pr` → `slack-pr-review-request`)? Skills that hand off to each other through their descriptions are fragile to renames and rewrites.
- **Plugin updates**: edits inside a plugin's cached skill files get overwritten when the plugin updates. Prefer settings, CLAUDE.md, or a personal wrapper skill.
- **Cost**: a routing skill or a stricter rule adds a step to every matching prompt. Mention it if that matters for quick requests.

## 7. Protecting Keeps

For each Keep, check that your proposals don't undermine it. For example, don't tell them to disable a skill they praised, and don't broaden a description that already triggers just right. If a proposal trades off against a Keep, say so explicitly.
