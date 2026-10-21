"""System prompt construction and the LLM tool-use loop."""

from __future__ import annotations

import sys

from . import skills, tools

DEFAULT_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 8192
DEFAULT_MAX_TURNS = 40


def build_system_prompt() -> str:
    profile = ""
    profile_path = tools.WORKSPACE / "CLAUDE.md"
    if profile_path.is_file():
        profile = profile_path.read_text(encoding="utf-8")

    catalog_lines = [
        f"- {s.name}: {s.description}" for s in skills.catalog() if s.description
    ]

    return f"""You are the AI Job Search agent, running locally in the workspace \
{tools.WORKSPACE}. You help the candidate find jobs, evaluate fit, draft applications, \
identify skill gaps, and prepare for interviews.

## Candidate profile (CLAUDE.md)
If the profile still contains [PLACEHOLDER] tokens, tell the user to fill them in \
(the /setup workflow of this repo) before doing profile-dependent work.

{profile}

## Available skills
Call load_skill(name) to get full workflow instructions before performing a task. \
Follow the loaded skill's steps.

{chr(10).join(catalog_lines)}

## Operating rules
- Prefer workspace files as the source of truth: tracked jobs, drafts, application \
records live under the repo (see list_files).
- Job search: load the scrape skill, pick portals that match the target market, call \
search_jobs with limit <= 25, then present matches with fit ratings.
- Fit evaluation: load job-application-assistant and follow its evaluation criteria.
- Writing output (CVs, cover letters, reports): write_file into the appropriate \
directory (cv/, cover_letters/, documents/, company_research/, upskill/).
- Be concise in chat; put long-form deliverables in files.
- Never invent job listings: results come only from search_jobs / job_detail.
- Ask before doing anything irreversible (e.g. submitting forms, sending email)."""


def run_turns(
    client,
    model: str,
    messages: list,
    system: str,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> None:
    """Run the tool-use loop until the model stops calling tools."""
    for turn in range(1, max_turns + 1):
        with client.messages.stream(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            tools=tools.TOOLS,
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
            final = stream.get_final_message()
        print()

        messages.append({"role": "assistant", "content": final.content})

        if final.stop_reason != "tool_use":
            if final.stop_reason == "max_tokens":
                print("[stopped: hit max_tokens mid-turn]", file=sys.stderr)
            return

        results = []
        for block in final.content:
            if block.type != "tool_use":
                continue
            print(
                f"  > {block.name}({', '.join(f'{k}={_short(v)}' for k, v in block.input.items())})",
                file=sys.stderr,
            )
            try:
                output = tools.dispatch(block.name, dict(block.input))
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": output}
                )
                print(f"    <- {len(output)} chars", file=sys.stderr)
            except tools.ToolError as exc:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(exc),
                        "is_error": True,
                    }
                )
                print(f"    <- error: {exc}", file=sys.stderr)
        messages.append({"role": "user", "content": results})

    print(f"[stopped: reached max turns ({max_turns})]", file=sys.stderr)


def _short(value) -> str:
    text = str(value)
    return text if len(text) <= 60 else text[:57] + "..."
