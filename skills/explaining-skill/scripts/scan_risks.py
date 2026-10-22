#!/usr/bin/env python3
"""Heuristic scan of a skill directory for behaviour worth a human look.

Usage: python3 -I scan_risks.py <skill_dir> [--plugin-root DIR]

This only reads files. It flags lines matching patterns grouped by category
(network, external hosts referenced anywhere, destructive file ops, credentials, code execution, obfuscation,
persistence/config changes, installs, prompt-level red flags). A hit is a
pointer for review, not a verdict; absence of hits is not proof of safety.
Prints JSON: {files, external_hosts: {host: [file:line]}, findings: {category: [{file, line, text}]}, extra}.
"""
import json
import re
import sys
from pathlib import Path

PATTERNS = {
    "network": r"\b(curl|wget|requests\.(get|post|put)|urllib|httpx|fetch\(|axios|socket\.|WebFetch|nc\s+-|Invoke-WebRequest|webhook|ngrok|pastebin)\b",
    "destructive_file_ops": r"(rm\s+-[a-zA-Z]*[rf]|shutil\.rmtree|os\.remove|unlink\(|git\s+(reset\s+--hard|clean\s+-[a-z]*f|push\s+(-f|--force))|>\s*/dev/sd|mkfs|dd\s+if=|truncate\s)",
    "credentials_and_secrets": r"(\.ssh/|id_rsa|\.aws/|\.netrc|\.npmrc|\.pypirc|\.env\b|credentials|api[_-]?key|secret|token|password|keychain|\.git-credentials|ANTHROPIC_API_KEY|GITHUB_TOKEN|printenv|os\.environ)",
    "code_execution": r"(\beval\(|\bexec\(|subprocess|os\.system|child_process|spawn\(|\bsh\s+-c|bash\s+-c|\|\s*(ba)?sh\b|pickle\.loads|__import__)",
    "obfuscation": r"(base64|b64decode|atob\(|fromCharCode|\\x[0-9a-fA-F]{2}.*\\x[0-9a-fA-F]{2}|codecs\.decode|zlib\.decompress|[A-Za-z0-9+/]{120,}={0,2})",
    "persistence_and_config": r"(\.bashrc|\.zshrc|\.profile|crontab|systemctl|launchctl|settings\.json|CLAUDE\.md|\.claude/|hooks?\b.*(PreToolUse|PostToolUse|SessionStart|UserPromptSubmit)|chmod\s+\+?[0-7]*[sx]|sudo\b)",
    "package_installs": r"\b(pip3?\s+install|npm\s+(i|install)\b|npx\s|uvx?\s|brew\s+install|apt(-get)?\s+install|cargo\s+install|go\s+install|gem\s+install)",
    "prompt_red_flags": r"(?i)(do not (tell|inform|mention|show)|without (asking|telling|confirm)|don't (tell|ask|mention)|silently|secretly|hide (this|the)|ignore (previous|prior|all|the user)|bypass|disable (safety|permission|sandbox)|dangerously|--dangerously|skip[- ]permissions|exfiltrat|override (the )?user)",
}
URL_RE = re.compile(r"""(?:https?|wss?)://([A-Za-z0-9.-]+\.[A-Za-z]{2,}|\[[0-9a-fA-F:]+\]|\d+\.\d+\.\d+\.\d+)""")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "example.com", "example.org"}
TEXT_EXT = {".md", ".py", ".sh", ".bash", ".js", ".mjs", ".cjs", ".ts", ".json", ".yaml", ".yml",
            ".toml", ".txt", ".html", ".ps1", ".rb", ".go", ".rs", ".cfg", ".ini", ""}


def scan_file(p: Path, base: Path, findings: dict, hosts: dict) -> None:
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    rel = str(p.relative_to(base))
    for n, line in enumerate(lines, 1):
        for host in URL_RE.findall(line):
            if host.lower() not in LOCAL_HOSTS:
                hosts.setdefault(host.lower(), []).append(f"{rel}:{n}")
        for cat, pat in PATTERNS.items():
            if re.search(pat, line):
                findings.setdefault(cat, []).append(
                    {"file": str(p.relative_to(base)), "line": n, "text": line.strip()[:200]})


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    base = Path(args[0]).expanduser().resolve()
    plugin_root = None
    if "--plugin-root" in args:
        plugin_root = Path(args[args.index("--plugin-root") + 1]).expanduser().resolve()

    files, findings, extra, hosts = [], {}, [], {}
    for p in sorted(base.rglob("*")):
        if ".git" in p.parts or not p.is_file():
            continue
        rel = str(p.relative_to(base))
        size = p.stat().st_size
        is_exec = bool(p.stat().st_mode & 0o111)
        files.append({"path": rel, "bytes": size, "executable": is_exec})
        if p.is_symlink():
            extra.append(f"symlink: {rel} -> {p.resolve()}")
        if p.suffix.lower() in TEXT_EXT and size < 2_000_000:
            scan_file(p, base, findings, hosts)
        elif p.suffix.lower() not in TEXT_EXT:
            extra.append(f"non-text/binary file (not scanned): {rel} ({size} bytes)")

    if plugin_root:
        for name in ("hooks/hooks.json", ".mcp.json", ".claude-plugin/plugin.json"):
            f = plugin_root / name
            if f.is_file():
                extra.append(f"plugin-level file present (review it, it runs outside the skill): {f}")
                scan_file(f, plugin_root, findings, hosts)

    # Every non-local host referenced anywhere. Most are doc links; the ones in
    # code, HTML templates (img/script/link src) or config are what matter.
    external = {h: locs[:10] for h, locs in sorted(hosts.items())}
    print(json.dumps({"skill_dir": str(base), "files": files, "external_hosts": external,
                      "findings": findings, "extra": extra},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
