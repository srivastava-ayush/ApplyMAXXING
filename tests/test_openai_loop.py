import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent import openai_loop


class OpenAILoopTests(unittest.TestCase):
    def test_tool_call_result_round_trip(self):
        call = SimpleNamespace(
            id="call_1", function=SimpleNamespace(name="read_file", arguments='{"path":"CLAUDE.md"}')
        )
        first = SimpleNamespace(
            content=None, tool_calls=[call],
            model_dump=lambda **kwargs: {"role": "assistant", "tool_calls": [
                {"id": "call_1", "type": "function", "function": {
                    "name": "read_file", "arguments": '{"path":"CLAUDE.md"}'}}
            ]},
        )
        second = SimpleNamespace(content="done", tool_calls=None,
                                 model_dump=lambda **kwargs: {"role": "assistant", "content": "done"})
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=Mock())))
        client.chat.completions.create.side_effect = [
            SimpleNamespace(choices=[SimpleNamespace(message=first)]),
            SimpleNamespace(choices=[SimpleNamespace(message=second)]),
        ]
        messages = [{"role": "user", "content": "read profile"}]
        with patch("agent.openai_loop.tools.dispatch", return_value="profile") as dispatch:
            openai_loop.run_turns(client, "gpt-4.1-mini", messages, "system")
        dispatch.assert_called_once_with("read_file", {"path": "CLAUDE.md"})
        self.assertEqual(messages[2], {"role": "tool", "tool_call_id": "call_1", "content": "profile"})
        self.assertEqual(client.chat.completions.create.call_args.kwargs["messages"][0],
                         {"role": "system", "content": "system"})


if __name__ == "__main__":
    unittest.main()
