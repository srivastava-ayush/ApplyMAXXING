# Agent Guidelines: AI Job Search

This workspace is a self-contained job-search agent.

- **The agent** is the `agent/` package: `python -m agent "<goal>"` runs an LLM tool loop (requires `ANTHROPIC_API_KEY` in `.venv`).
- **Candidate profile:** [CLAUDE.md](CLAUDE.md) — the agent injects it into its system prompt.
- **Workflow skills:** [.claude/skills/](.claude/skills/) (scrape, apply, upskill) and portal-search skills with CLIs under [.agents/skills/](.agents/skills/) — the agent loads these via its `load_skill` tool and calls the CLIs via its `search_jobs` / `job_detail` tools.
- **Workspace data:** `cv/`, `cover_letters/`, `documents/`, `company_research/`, `upskill/`, `job_scraper/` (dedup state for the scrape skill).
- **Reinstall portal CLIs:** `python3 tools/install_portal_clis.py`
- **Tests:** `python3 -m unittest discover -s tests -t .`
