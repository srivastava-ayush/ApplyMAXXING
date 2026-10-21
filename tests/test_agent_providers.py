import io
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent import __main__ as cli


class ProviderSelectionTests(unittest.TestCase):
    def test_missing_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("agent.tools.WORKSPACE", Path(directory)), patch.dict(os.environ, {}, clear=True):
                with patch("sys.stderr", new_callable=io.StringIO) as err:
                    self.assertEqual(cli.main(["hello"]), 2)
                    self.assertIn("no API key set", err.getvalue())

    def test_load_key_from_ignored_env(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / ".env").write_text("GEMINI_API_KEY=local-test-key\n")
            with patch("agent.tools.WORKSPACE", Path(directory)), patch.dict(os.environ, {}, clear=True):
                cli._load_local_keys()
                self.assertEqual(os.environ["GEMINI_API_KEY"], "local-test-key")

    def test_load_openai_key_without_overriding_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / ".env").write_text("OPENAI_API_KEY=file-key\nGEMINI_API_KEY=gemini-key\n")
            with patch("agent.tools.WORKSPACE", Path(directory)), patch.dict(os.environ, {"OPENAI_API_KEY": "shell-key"}, clear=True):
                cli._load_local_keys()
                self.assertEqual(os.environ["OPENAI_API_KEY"], "shell-key")
                self.assertEqual(os.environ["GEMINI_API_KEY"], "gemini-key")

    def test_anthropic_takes_precedence(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "a", "GEMINI_API_KEY": "g"}, clear=True):
            with patch.dict("sys.modules", {"anthropic": SimpleNamespace(Anthropic=Mock())}):
                with patch("agent.loop.run_turns") as run, patch("agent.loop.build_system_prompt", return_value="system"):
                    self.assertEqual(cli.main(["hello"]), 0)
                    self.assertEqual(run.call_args.args[1], "claude-sonnet-4-5")

    @unittest.skipUnless(importlib.util.find_spec("openai"), "openai not installed")
    def test_explicit_openai_selection(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "g", "OPENAI_API_KEY": "o"}, clear=True):
            with patch("openai.OpenAI") as client, patch("agent.openai_loop.run_turns") as run:
                self.assertEqual(cli.main(["--provider", "openai", "hello"]), 0)
                client.assert_called_once_with(api_key="o")
                self.assertEqual(run.call_args.args[1], "gpt-4.1-mini")

    @unittest.skipUnless(importlib.util.find_spec("openai"), "openai not installed")
    def test_interactive_mode_keeps_conversation(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "o"}, clear=True):
            with patch("openai.OpenAI"), patch("agent.openai_loop.run_turns") as run:
                with patch("sys.stdin.isatty", return_value=True):
                    with patch("builtins.input", side_effect=["first", "follow up", "/exit"]):
                        with patch("sys.stdout", new_callable=io.StringIO):
                            self.assertEqual(cli.main(["--provider", "openai"]), 0)
                self.assertEqual(run.call_count, 2)
                self.assertEqual(run.call_args.args[2], [
                    {"role": "user", "content": "first"},
                    {"role": "user", "content": "follow up"},
                ])

    def test_explicit_provider_requires_its_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("agent.tools.WORKSPACE", Path(directory)), patch.dict(os.environ, {"GEMINI_API_KEY": "g"}, clear=True):
                with patch("sys.stderr", new_callable=io.StringIO) as err:
                    self.assertEqual(cli.main(["--provider", "openai", "hello"]), 2)
                    self.assertIn("OPENAI_API_KEY is not set", err.getvalue())


try:
    from agent import gemini_loop
    from google.genai import types
except ImportError:
    gemini_loop = None


@unittest.skipIf(gemini_loop is None, "google-genai not installed")
class GeminiLoopTests(unittest.TestCase):
    def test_tool_call_and_result(self):
        call = types.Part.from_function_call(name="read_file", args={"path": "CLAUDE.md"})
        first = types.Content(role="model", parts=[call])
        second = types.Content(role="model", parts=[types.Part.from_text(text="done")])
        client = SimpleNamespace(models=Mock())
        client.models.generate_content.side_effect = [
            SimpleNamespace(candidates=[SimpleNamespace(content=first)]),
            SimpleNamespace(candidates=[SimpleNamespace(content=second)]),
        ]
        messages = [types.Content(role="user", parts=[types.Part.from_text(text="read profile")])]
        with patch("agent.gemini_loop.tools.dispatch", return_value="profile") as dispatch:
            gemini_loop.run_turns(client, "gemini-3.8-flash", messages, "system")
        dispatch.assert_called_once_with("read_file", {"path": "CLAUDE.md"})
        self.assertIs(messages[1], first)
        self.assertEqual(messages[2].parts[0].function_response.response, {"result": "profile"})
        self.assertEqual(len(client.models.generate_content.call_args_list), 2)

    def test_gemini_selected_with_only_gemini_key(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "g"}, clear=True):
            with patch("google.genai.Client") as client, patch("agent.gemini_loop.run_turns") as run:
                self.assertEqual(cli.main(["hello"]), 0)
                client.assert_called_once_with(api_key="g")
                self.assertEqual(run.call_args.args[1], "gemini-3.8-flash")
                self.assertEqual(run.call_args.args[2][0].parts[0].text, "hello")


if __name__ == "__main__":
    unittest.main()
