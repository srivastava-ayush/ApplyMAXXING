"""Gemini tool-use loop using the same workspace tools as the Anthropic loop."""

from __future__ import annotations

import sys

from google.genai import types

from . import loop, tools

DEFAULT_MODEL = "gemini-3.8-flash"


def run_turns(client, model: str, messages: list, system: str, max_turns: int = loop.DEFAULT_MAX_TURNS) -> None:
    """Run a turn, retaining Gemini's content parts (including thought signatures)."""
    declarations = [
        types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters_json_schema=tool["input_schema"],
        )
        for tool in tools.TOOLS
    ]
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=loop.MAX_TOKENS,
        tools=[types.Tool(function_declarations=declarations)],
    )

    for _ in range(max_turns):
        response = client.models.generate_content(model=model, contents=messages, config=config)
        if not response.candidates or not response.candidates[0].content:
            print("[stopped: Gemini returned no content]", file=sys.stderr)
            return
        content = response.candidates[0].content
        messages.append(content)
        calls = []
        for part in content.parts or []:
            if part.text:
                print(part.text, end="", flush=True)
            if part.function_call:
                calls.append(part.function_call)
        print()

        if not calls:
            return

        results = []
        for call in calls:
            args = dict(call.args or {})
            print(f"  > {call.name}({', '.join(f'{k}={loop._short(v)}' for k, v in args.items())})", file=sys.stderr)
            try:
                output = tools.dispatch(call.name, args)
                result = {"result": output}
                print(f"    <- {len(output)} chars", file=sys.stderr)
            except tools.ToolError as exc:
                result = {"error": str(exc)}
                print(f"    <- error: {exc}", file=sys.stderr)
            results.append(types.Part.from_function_response(name=call.name, response=result))
        messages.append(types.Content(role="user", parts=results))

    print(f"[stopped: reached max turns ({max_turns})]", file=sys.stderr)
