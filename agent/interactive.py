"""Small terminal interface for a persistent agent conversation."""

from __future__ import annotations

from . import skills

HELP = """Commands:
  /help     Show these commands
  /status   Show provider, model, and conversation length
  /skills   List available workflows
  /clear    Start a fresh conversation (does not delete workspace files)
  /exit     Quit (Ctrl-D also works)

Ask in plain language to search jobs, evaluate a posting, draft an application,
or identify skill gaps. Follow-up messages retain this session's context.
"""


def run(provider: str, model: str, messages: list, ask) -> int:
    """Read turns until exit; ask(prompt) runs one provider turn."""
    print(f"AI Job Search | {provider} / {model}\nType /help for commands or /exit to quit.")
    while True:
        try:
            prompt = input("you> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("\nType /exit to quit.")
            continue

        if not prompt:
            continue
        command = prompt.lower()
        if command in {"/exit", "/quit"}:
            return 0
        if command == "/help":
            print(HELP)
        elif command == "/status":
            print(f"Provider: {provider} | Model: {model} | Messages: {len(messages)}")
        elif command == "/skills":
            for skill in skills.catalog():
                print(f"  {skill.name}: {skill.description}")
        elif command == "/clear":
            messages.clear()
            print("Conversation cleared. Workspace files are unchanged.")
        elif prompt.startswith("/"):
            print("Unknown command. Type /help for available commands.")
        else:
            try:
                ask(prompt)
            except KeyboardInterrupt:
                print("\n[request interrupted; type /exit to quit]")
