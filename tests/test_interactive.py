import io
import unittest
from unittest.mock import patch

from agent import interactive


class InteractiveTests(unittest.TestCase):
    def test_commands_followups_and_clear(self):
        messages = []
        calls = []

        def ask(prompt):
            calls.append(prompt)
            messages.append({"role": "user", "content": prompt})

        with patch("builtins.input", side_effect=["first", "follow up", "/status", "/clear", "/status", "/exit"]):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(interactive.run("openai", "gpt-4.1-mini", messages, ask), 0)
        self.assertEqual(calls, ["first", "follow up"])
        self.assertEqual(messages, [])
        self.assertIn("Provider: openai | Model: gpt-4.1-mini | Messages: 2", output.getvalue())
        self.assertIn("Messages: 0", output.getvalue())

    def test_interrupt_and_eof(self):
        with patch("builtins.input", side_effect=[KeyboardInterrupt, EOFError]):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(interactive.run("gemini", "model", [], lambda prompt: None), 0)
        self.assertIn("Type /exit to quit", output.getvalue())

    def test_unknown_command_does_not_go_to_model(self):
        with patch("builtins.input", side_effect=["/wrong", "/exit"]):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                interactive.run("openai", "model", [], lambda prompt: self.fail("unexpected model call"))
        self.assertIn("Unknown command", output.getvalue())


if __name__ == "__main__":
    unittest.main()
