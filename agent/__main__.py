"""Entry point: python -m agent "find me data engineer jobs in Copenhagen"."""

from __future__ import annotations

import argparse
import os
import sys

from . import interactive, loop, skills, tools


def _load_local_keys() -> None:
    """Read provider keys from the ignored .env without overriding shell values."""
    env_file = tools.WORKSPACE / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() in {"GEMINI_API_KEY", "OPENAI_API_KEY"}:
            os.environ.setdefault(name.strip(), value.strip().strip('"\''))


def _test_tools() -> int:
    print("== skills ==")
    for skill in skills.catalog():
        print(f"  {skill.name}")
    print("\n== search_jobs(jobindex, query=python, limit=3) ==")
    print(tools.dispatch("search_jobs", {"portal": "jobindex", "query": "python", "limit": 3})[:1500])
    print("\n== read_file(CLAUDE.md) first 300 chars ==")
    print(tools.dispatch("read_file", {"path": "CLAUDE.md"})[:300])
    print("\n== list_files() ==")
    print(tools.dispatch("list_files", {}))
    print("\nall tool dispatches OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent",
        description=(
            "Run the AI Job Search agent. Wraps the workspace's portal CLIs, skills, "
            "and profile files in an LLM tool loop. Uses Anthropic, Gemini, or OpenAI."
        ),
        epilog='examples:\n'
        '  python -m agent "find me senior python jobs in Copenhagen"\n'
        '  python -m agent "evaluate https://jobindex.dk/view/123 against my profile"\n'
        '  python -m agent --provider openai  # interactive mode\n'
        "  python -m agent --list-skills\n"
        "  python -m agent --test-tools   # exercise tool dispatch without an API key",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("prompt", nargs="*", help="goal for the agent (omit for interactive mode)")
    parser.add_argument("--model", default=os.environ.get("AGENT_MODEL"))
    parser.add_argument("--provider", choices=("anthropic", "gemini", "openai"),
                        help="select a provider (default: first configured of Anthropic, Gemini, OpenAI)")
    parser.add_argument("--max-turns", type=int, default=loop.DEFAULT_MAX_TURNS)
    parser.add_argument("--list-skills", action="store_true", help="print the skill catalog and exit")
    parser.add_argument("--test-tools", action="store_true", help="run tool dispatch self-tests without an API key")
    args = parser.parse_args(argv)

    if args.list_skills:
        for skill in skills.catalog():
            print(f"{skill.name}: {skill.description}")
        return 0

    if args.test_tools:
        return _test_tools()

    _load_local_keys()
    keys = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}
    provider = args.provider or next((name for name, key in keys.items() if os.environ.get(key)), None)
    if provider is None or not os.environ.get(keys[provider]):
        print(
            f"error: {keys[provider]} is not set.\n" if provider else
            "error: no API key set (ANTHROPIC_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY).\n"
            "Set a key in your environment or in the ignored .env file.\n"
            "(or run with --test-tools / --list-skills, which need no key)",
            file=sys.stderr,
        )
        return 2

    if provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            print("error: install the Anthropic SDK with pip install anthropic", file=sys.stderr)
            return 2
        client = anthropic.Anthropic()
        run_turns = loop.run_turns
        model = args.model or loop.DEFAULT_MODEL
    elif provider == "gemini":
        try:
            from google import genai
            from . import gemini_loop
        except ImportError:
            print("error: install the Gemini SDK with pip install google-genai", file=sys.stderr)
            return 2
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        run_turns = gemini_loop.run_turns
        model = args.model or gemini_loop.DEFAULT_MODEL
    else:
        try:
            import openai
            from . import openai_loop
        except ImportError:
            print("error: install the OpenAI SDK with pip install openai", file=sys.stderr)
            return 2
        client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        run_turns = openai_loop.run_turns
        model = args.model or openai_loop.DEFAULT_MODEL

    system = loop.build_system_prompt()
    messages: list = []

    def ask(prompt: str) -> None:
        start = len(messages)
        try:
            if provider == "gemini":
                from google.genai import types

                messages.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))
            else:
                messages.append({"role": "user", "content": prompt})
            run_turns(client, model, messages, system, args.max_turns)
        except (Exception, KeyboardInterrupt):
            # A failed API turn must not leave an unanswered user message or
            # partial tool results in the next request's conversation.
            del messages[start:]
            raise

    def api_error(exc: Exception) -> bool:
        if provider == "gemini":
            from google.genai import errors

            if isinstance(exc, errors.APIError):
                print(f"Gemini API error: {exc}", file=sys.stderr)
                return True
        if provider == "openai" and isinstance(exc, openai.APIError):
            print(f"OpenAI API error: {exc}", file=sys.stderr)
            return True
        if provider == "anthropic" and isinstance(exc, anthropic.APIError):
            print(f"Anthropic API error: {exc}", file=sys.stderr)
            return True
        return False

    try:
        if not args.prompt:
            if not sys.stdin.isatty():
                print("no prompt given (interactive mode only when stdin is a TTY)", file=sys.stderr)
                return 2

            def interactive_ask(prompt: str) -> None:
                try:
                    ask(prompt)
                except Exception as exc:
                    if not api_error(exc):
                        raise

            return interactive.run(provider, model, messages, interactive_ask)
        ask(" ".join(args.prompt))
        return 0
    except KeyboardInterrupt:
        print("\n[interrupted]", file=sys.stderr)
        return 130
    except Exception as exc:
        if api_error(exc):
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
