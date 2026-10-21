"""Tool schemas and dispatch for the agent loop.

Every tool either wraps an existing workspace utility (portal CLIs,
salary_lookup.py, skills, files) or is a workspace-scoped file operation.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import skills

WORKSPACE = Path(__file__).resolve().parent.parent

MAX_RESULT_CHARS = 60_000
CLI_TIMEOUT_SECONDS = 90

PORTALS: dict[str, dict[str, str | None]] = {
    "jobindex": {
        "dir": ".agents/skills/jobindex-search/cli",
        "query_flag": "query",
        "location_flag": None,
    },
    "jobnet": {
        "dir": ".agents/skills/jobnet-search/cli",
        "query_flag": "search-string",
        "location_flag": None,
    },
    "jobbank": {
        "dir": ".agents/skills/jobbank-search/cli",
        "query_flag": "key",
        "location_flag": None,
    },
    "jobdanmark": {
        "dir": ".agents/skills/jobdanmark-search/cli",
        "query_flag": "text",
        "location_flag": "municipality",
    },
    "linkedin": {
        "dir": ".agents/skills/linkedin-search/cli",
        "query_flag": "query",
        "location_flag": "location",
    },
    "freehire": {
        "dir": ".agents/skills/freehire-search/cli",
        "query_flag": "query",
        "location_flag": None,
    },
}

DENIED_PARTS = {".git", "node_modules", ".venv", "__pycache__"}


class ToolError(Exception):
    pass


def _truncate(text: str) -> str:
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return text[:MAX_RESULT_CHARS] + f"\n\n[truncated at {MAX_RESULT_CHARS} chars]"


def resolve_path(path: str) -> Path:
    candidate = Path(path)
    target = candidate if candidate.is_absolute() else WORKSPACE / candidate
    target = target.resolve()
    if target != WORKSPACE and WORKSPACE not in target.parents:
        raise ToolError(f"path escapes the workspace: {path}")
    rel = target.relative_to(WORKSPACE)
    if DENIED_PARTS.intersection(rel.parts):
        raise ToolError(f"path is in a denied directory: {path}")
    return target


def _flatten_extra(extra: dict) -> list[str]:
    args: list[str] = []
    for key, value in (extra or {}).items():
        flag = key if key.startswith("--") else f"--{key}"
        if value is True:
            args.append(flag)
        elif value in (False, None, ""):
            continue
        elif isinstance(value, list):
            for item in value:
                args += [flag, str(item)]
        else:
            args += [flag, str(value)]
    return args


def build_search_args(
    portal: str,
    query: str | None,
    location: str | None,
    limit: int | None,
    extra: dict | None,
) -> tuple[list[str], list[str]]:
    cfg = PORTALS.get(portal)
    if cfg is None:
        raise ToolError(f"unknown portal {portal!r}; choose from {', '.join(PORTALS)}")
    notes: list[str] = []
    args = ["search"]
    if query and cfg["query_flag"]:
        args += [f"--{cfg['query_flag']}", query]
    if location:
        if cfg["location_flag"]:
            args += [f"--{cfg['location_flag']}", location]
        else:
            notes.append(
                f"note: {portal} has no generic location flag; location "
                f"{location!r} was NOT applied - filter via `extra` per the "
                f"portal's skill (e.g. region/country/city flags)"
            )
    if limit:
        args += ["--limit", str(int(limit))]
    args += _flatten_extra(extra or {})
    if portal == "linkedin" and "--location" not in args:
        raise ToolError("linkedin search requires a location")
    return args, notes


def _run_cli(portal: str, args: list[str]) -> str:
    cfg = PORTALS[portal]
    cli_dir = WORKSPACE / cfg["dir"]
    if not cli_dir.is_dir():
        raise ToolError(f"CLI for {portal} not installed at {cfg['dir']}")
    cmd = ["bun", "run", "src/cli.ts", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=cli_dir,
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"{portal} CLI timed out after {CLI_TIMEOUT_SECONDS}s")
    output = proc.stdout.strip()
    if proc.returncode != 0:
        detail = (proc.stderr or output or "no output").strip()
        raise ToolError(f"{portal} CLI exited {proc.returncode}: {detail[:4000]}")
    if not output:
        raise ToolError(f"{portal} CLI produced no output")
    return output


def _salary_lookup(company: str, city: str | None) -> str:
    script = WORKSPACE / "salary_lookup.py"
    cmd = ["python3", str(script), company, "--json"]
    if city:
        cmd += ["--city", city]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise ToolError(output.strip() or f"salary_lookup exited {proc.returncode}")
    return output.strip()


def _read_file(path: str) -> str:
    target = resolve_path(path)
    if not target.is_file():
        raise ToolError(f"not a file: {path}")
    text = target.read_text(encoding="utf-8", errors="replace")
    return _truncate(text)


def _list_files(path: str | None) -> str:
    root = resolve_path(path) if path else WORKSPACE
    if not root.is_dir():
        raise ToolError(f"not a directory: {path}")
    entries: list[str] = []
    for item in sorted(root.iterdir()):
        if item.name in DENIED_PARTS:
            continue
        suffix = "/" if item.is_dir() else ""
        entries.append(f"{item.name}{suffix}")
        if len(entries) >= 500:
            entries.append("... (capped at 500 entries)")
            break
    return "\n".join(entries) or "(empty directory)"


def _write_file(path: str, content: str) -> str:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    rel = target.relative_to(WORKSPACE)
    return f"wrote {len(content)} chars to {rel}"


TOOLS: list[dict] = [
    {
        "name": "search_jobs",
        "description": (
            "Search a job portal for listings. Returns raw CLI JSON. "
            "Portals: jobindex (DK), jobnet (DK, public sector), jobbank (DK, RSS), "
            "jobdanmark (DK), linkedin (global, location REQUIRED), freehire (global tech). "
            "Portal flag cheat-sheet for `extra` keys (each key becomes --key): "
            "jobindex: jobage, sort, page; "
            "jobnet: order, region, work-hours, duration, postal-code, radius, page, per-page; "
            "jobbank: exclude, type, location, remote(helt|delvist), since; "
            "jobdanmark: zip, region, job-type(fuldtid|deltid|...), page; "
            "linkedin: jobage, remote(remote|hybrid|onsite), page; "
            "freehire: jobage, region, country, city, seniority, category, skill, remote. "
            "Read the portal's skill (load_skill) for full flag documentation. "
            "Always pass limit <= 25 to keep results small."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "portal": {"type": "string", "enum": list(PORTALS)},
                "query": {"type": "string", "description": "Free-text keywords"},
                "location": {
                    "type": "string",
                    "description": "Location (linkedin: required; jobdanmark: municipality; others: use extra)",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                "extra": {
                    "type": "object",
                    "description": "Portal-specific flags, e.g. {\"jobage\": 7, \"remote\": \"remote\"}",
                },
            },
            "required": ["portal"],
        },
    },
    {
        "name": "job_detail",
        "description": "Fetch the full posting for a job id or URL from a portal. Returns raw CLI JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "portal": {"type": "string", "enum": list(PORTALS)},
                "id_or_url": {"type": "string"},
            },
            "required": ["portal", "id_or_url"],
        },
    },
    {
        "name": "load_skill",
        "description": (
            "Load the full instructions for a workflow skill before performing it "
            "(e.g. scrape, job-application-assistant, upskill, jobindex-search). "
            "Call this first for any multi-step task."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file inside the workspace (candidate profile, CV, drafts, tracked jobs).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path relative to the workspace root"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List entries of a workspace directory (defaults to the workspace root).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
    },
    {
        "name": "write_file",
        "description": "Write a file inside the workspace (drafts, application records, reports). Overwrites existing files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the workspace root"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "salary_lookup",
        "description": "Look up salary benchmarks for a company from salary_data.json (optional city filter).",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "city": {"type": "string"},
            },
            "required": ["company"],
        },
    },
]


def dispatch(name: str, args: dict) -> str:
    try:
        if name == "search_jobs":
            cli_args, notes = build_search_args(
                args.get("portal"),
                args.get("query"),
                args.get("location"),
                args.get("limit"),
                args.get("extra"),
            )
            result = _run_cli(args["portal"], cli_args)
            if notes:
                result += "\n\n" + "\n".join(notes)
            return _truncate(result)
        if name == "job_detail":
            portal = args.get("portal")
            if portal not in PORTALS:
                raise ToolError(f"unknown portal {portal!r}")
            return _truncate(_run_cli(portal, ["detail", args["id_or_url"]]))
        if name == "load_skill":
            return skills.load(args["name"])
        if name == "read_file":
            return _read_file(args["path"])
        if name == "list_files":
            return _list_files(args.get("path"))
        if name == "write_file":
            return _write_file(args["path"], args["content"])
        if name == "salary_lookup":
            return _salary_lookup(args["company"], args.get("city"))
        raise ToolError(f"unknown tool {name!r}")
    except KeyError as exc:
        if name == "load_skill":
            raise ToolError(str(exc)) from exc
        raise
    except (ValueError, TypeError) as exc:
        raise ToolError(f"bad arguments for {name}: {exc}") from exc
