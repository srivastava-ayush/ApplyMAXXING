"""OpenAI chat-completions tool loop for the shared workspace tools."""

from __future__ import annotations

import json
import sys

from . import loop, tools

DEFAULT_MODEL = "gpt-4.1-mini"


def run_turns(client, model: str, messages: list, system: str, max_turns: int = loop.DEFAULT_MAX_TURNS) -> None:
    declarations = [
        {"type": "function", "function": {
            "name": tool["name"], "description": tool["description"],
            "parameters": tool["input_schema"],
        }} for tool in tools.TOOLS
    ]
    for _ in range(max_turns):
        response = client.chat.completions.create(
            model=model, messages=[{"role": "system", "content": system}, *messages],
            tools=declarations,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        if message.content:
            print(message.content, end="", flush=True)
        print()
        if not message.tool_calls:
            return
        for call in message.tool_calls:
            try:
                args = json.loads(call.function.arguments)
                if not isinstance(args, dict):
                    raise ValueError("tool arguments must be an object")
                print(f"  > {call.function.name}({', '.join(f'{k}={loop._short(v)}' for k, v in args.items())})", file=sys.stderr)
                output = tools.dispatch(call.function.name, args)
                print(f"    <- {len(output)} chars", file=sys.stderr)
            except (ValueError, tools.ToolError) as exc:
                output = f"error: {exc}"
                print(f"    <- {output}", file=sys.stderr)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
    print(f"[stopped: reached max turns ({max_turns})]", file=sys.stderr)
