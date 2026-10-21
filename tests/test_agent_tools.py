import unittest

from agent import skills, tools


class SkillCatalogTests(unittest.TestCase):
    def test_known_skills_discovered(self):
        names = {s.name for s in skills.catalog()}
        self.assertIn("scrape", names)
        self.assertIn("jobindex-search", names)
        self.assertIn("job-application-assistant", names)

    def test_every_skill_has_description(self):
        for skill in skills.catalog():
            self.assertTrue(skill.description, f"{skill.name} missing description")

    def test_load_skill_by_name(self):
        text = skills.load("scrape")
        self.assertIn("scrape", text.lower())

    def test_load_unknown_skill_raises(self):
        with self.assertRaises(KeyError):
            skills.load("does-not-exist")


class PathGuardTests(unittest.TestCase):
    def test_rejects_escape(self):
        with self.assertRaises(tools.ToolError):
            tools.resolve_path("../../etc/passwd")

    def test_rejects_absolute_outside(self):
        with self.assertRaises(tools.ToolError):
            tools.resolve_path("/etc/passwd")

    def test_rejects_dot_git(self):
        with self.assertRaises(tools.ToolError):
            tools.resolve_path(".git/config")

    def test_allows_workspace_file(self):
        self.assertTrue(tools.resolve_path("CLAUDE.md").exists())


class CliArgTests(unittest.TestCase):
    def test_jobindex_search_args(self):
        args, notes = tools.build_search_args("jobindex", "python", "Copenhagen", 5, {"jobage": 7})
        self.assertEqual(args, ["search", "--query", "python", "--limit", "5", "--jobage", "7"])
        self.assertEqual(len(notes), 1)

    def test_linkedin_requires_location(self):
        with self.assertRaises(tools.ToolError):
            tools.build_search_args("linkedin", "data", None, 5, {})

    def test_linkedin_location(self):
        args, notes = tools.build_search_args("linkedin", "data", "Copenhagen, Denmark", 5, {})
        self.assertIn("--location", args)
        self.assertEqual(notes, [])

    def test_extra_booleans_and_lists(self):
        args, _ = tools.build_search_args("jobnet", "nurse", None, None, {"remote": True, "type": [3, 6]})
        self.assertIn("--remote", args)
        self.assertEqual(args[args.index("--type") :], ["--type", "3", "--type", "6"])

    def test_unknown_portal(self):
        with self.assertRaises(tools.ToolError):
            tools.build_search_args("monster", "x", None, None, None)


class DispatchTests(unittest.TestCase):
    def test_unknown_tool(self):
        with self.assertRaises(tools.ToolError):
            tools.dispatch("warp_drive", {})

    def test_write_read_list_roundtrip(self):
        tools.dispatch("write_file", {"path": "documents/_agent_test.txt", "content": "hello"})
        try:
            self.assertEqual(tools.dispatch("read_file", {"path": "documents/_agent_test.txt"}), "hello")
            listing = tools.dispatch("list_files", {"path": "documents"})
            self.assertIn("_agent_test.txt", listing)
        finally:
            tools.resolve_path("documents/_agent_test.txt").unlink()

    def test_read_missing_file_errors(self):
        with self.assertRaises(tools.ToolError):
            tools.dispatch("read_file", {"path": "no/such/file.txt"})

    def test_load_skill_dispatch(self):
        self.assertIn("Job", tools.dispatch("load_skill", {"name": "jobindex-search"}))


if __name__ == "__main__":
    unittest.main()
