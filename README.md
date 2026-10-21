# AI Job Search — Autonomous Job-Search Agent

A self-contained job-search agent that runs on your machine. It searches live job
portals, evaluates fit against your profile, drafts tailored CVs and cover letters,
identifies skill gaps, and keeps its own dedup/application state.

This repo is **not** a library or a web app — it is a workspace plus a small agent
runtime (`agent/`) that drives it. Every capability is a *skill* (markdown
instructions) paired with a *tool* (a CLI or script the agent calls).

```
python -m agent "find me senior python jobs in Copenhagen"
```

---

## Requirements

| Requirement | Why | Install |
|---|---|---|
| Python 3.10+ | Agent runtime + helper scripts | system package manager |
| `anthropic`, `google-genai`, or `openai` (in `.venv`) | LLM tool-use loop | Install the SDK for your chosen provider with `.venv/bin/pip install <package>` |
| [Bun](https://bun.sh) | Runs the portal-search CLIs (TypeScript) | `curl -fsSL https://bun.sh/install \| bash` |
| `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or `OPENAI_API_KEY` | Model calls (default order: Anthropic, Gemini, OpenAI) | export in your shell, or use `.env` for Gemini/OpenAI |
| LaTeX (`lualatex`, `xelatex`) | Compiles CVs / cover letters to PDF | TeX Live / MacTeX / TinyTeX |
| `pypdf` *(optional)* | ATS text-layer check in `tools/verify_pdf.py` | `pip install pypdf` |

---

## Quick start

```bash
# 1. Install the portal CLIs (idempotent; discovers every .agents/skills/*/cli)
python3 tools/install_portal_clis.py

# 2. Set up the Python environment
python3 -m venv .venv
.venv/bin/pip install anthropic

# 3. Fill in your profile: edit CLAUDE.md (replace every [PLACEHOLDER] token)

# 4. Run
source .venv/bin/activate
export ANTHROPIC_API_KEY=sk-ant-...
python -m agent "find new data engineer roles in Denmark and rank them"
```

To use Gemini instead, leave `ANTHROPIC_API_KEY` unset, install `google-genai`,
and export `GEMINI_API_KEY` or put `GEMINI_API_KEY=your-key` in the repo's
git-ignored `.env` file. An environment variable takes precedence over `.env`.
The default Gemini model is `gemini-3.8-flash`;
`--model` or `AGENT_MODEL` overrides the selected provider's default. When both
keys are present, Anthropic is used.

To use OpenAI, install `.venv/bin/pip install openai`, put `OPENAI_API_KEY=your-key`
in the ignored `.env` file (or export it), and run:

```bash
.venv/bin/python -m agent --provider openai "find software developer jobs in Copenhagen"
```

The OpenAI default is `gpt-4.1-mini`. `--provider` selects any configured provider
explicitly; `--model` chooses a model for that provider.

No API key needed for the self-checks:

```bash
python -m agent --list-skills     # print the skill catalog
python -m agent --test-tools      # exercise tool dispatch end-to-end
python -m unittest discover -s tests -t .   # run the test suite
```

Interactive mode (no prompt argument, TTY stdin) keeps a conversation open across
turns. One-shot mode (a prompt argument) runs the goal and exits.

For an interactive terminal session with the OpenAI key configured:

```bash
.venv/bin/python -m agent --provider openai
```

Ask follow-up questions directly. `/help` lists commands; `/status` displays
the provider/model, `/skills` lists workflows, `/clear` resets the conversation
without deleting workspace files, and `/exit` quits. Ctrl-D also quits. API
errors are reported without losing the current interactive session.

---

## Architecture

The agent is a classic tool-use loop:

```
user goal
   │
   ▼
system prompt = role + candidate profile (CLAUDE.md) + skill catalog
   │
   ▼
┌─────────────────────────────────────────────┐
│  LLM turn (streamed)                        │
│    • may return text  → printed             │
│    • may request tool_use blocks            │
│         │                                   │
│         ▼                                   │
│    dispatch(tool, args)  ── tool_result ──┐ │
│                                          │ │
└──────────────────────────────────────────┼─┘
   ▲                                       │
   └───────────────────────────────────────┘
        loop until stop_reason != tool_use
```

The model decides *which* skill to load and *which* portal to search. The runtime
only enforces guardrails: workspace-scoped file paths, result truncation, timeouts,
and a max-turns cap.

---

## Component reference

### `agent/` — the runtime

| File | Responsibility |
|---|---|
| `agent/__main__.py` | CLI entry point. Parses args, builds the Anthropic client, drives one-shot or interactive mode. Flags: `--model`, `--max-turns`, `--list-skills`, `--test-tools`. |
| `agent/loop.py` | System-prompt construction (injects `CLAUDE.md` + skill catalog) and `run_turns()`, the streaming tool-use loop. Prints assistant text to stdout and tool activity to stderr. |
| `agent/tools.py` | Tool schemas (Anthropic format) and `dispatch()`. Wraps the portal CLIs, `salary_lookup.py`, skill loading, and sandboxed file I/O. Owns the workspace path guard and the portal flag registry. |
| `agent/skills.py` | Discovers every `*/SKILL.md` under the skill roots, parses YAML-style frontmatter (`name`, `description`), and loads a skill body by name. |

**Guardrails in `tools.py`:**

- `resolve_path()` rejects anything outside the workspace and any path inside
  `.git/`, `node_modules/`, `.venv/`, `__pycache__/`.
- Tool output is truncated at `MAX_RESULT_CHARS` (60 000).
- CLIs run with a 90 s timeout; `salary_lookup` with 60 s.
- Unknown tools / bad arguments raise `ToolError`, which is returned to the model
  as an `is_error` tool result rather than crashing the loop.

### Agent tools

| Tool | What it does | Backed by |
|---|---|---|
| `search_jobs` | Search a portal for listings; returns raw CLI JSON. Arguments: `portal`, `query`, `location`, `limit` (≤ 25), `extra` (portal-specific flags). | A portal CLI (below) |
| `job_detail` | Fetch the full posting for an id/URL from a portal. | A portal CLI |
| `load_skill` | Return the full markdown instructions of a workflow skill. | `agent/skills.py` |
| `read_file` | Read a workspace file (profile, CV, drafts, state). | sandboxed read |
| `write_file` | Write a workspace file (drafts, reports, application records). | sandboxed write |
| `list_files` | List a workspace directory (capped at 500 entries). | sandboxed read |
| `salary_lookup` | Look up salary benchmarks for a company (optional city). | `salary_lookup.py` |

### `.agents/skills/` — portal-search skills (each with a CLI)

Portable Agent Skills (a `SKILL.md` + a `cli/` written in TypeScript, run with Bun).
`search_jobs` maps its generic arguments onto each portal's flags.

| Skill | Market | Notes |
|---|---|---|
| `jobindex-search` | Denmark (all sectors) | Ships **disabled** (demo portal); enable in its `SKILL.md` or set `enabled: true`. |
| `jobnet-search` | Denmark (public sector) | Government portal (STAR). |
| `jobbank-search` | Denmark (academic) | Akademikernes Jobbank, RSS-backed. |
| `jobdanmark-search` | Denmark (broad) | Category / municipality / job-type filters. |
| `linkedin-search` | Global (any location) | `search` requires a `location`; personal use, keep volume low. |
| `freehire-search` | Global (tech) | Aggregates ~50 ATS platforms; tech-first faceted filters. |

Each CLI exposes `search` and `detail`. Run one directly with:

```bash
bun run .agents/skills/jobindex-search/cli/src/cli.ts search --query python --limit 5
bun run .agents/skills/jobindex-search/cli/src/cli.ts --help
```

### `.claude/skills/` — workflow skills

| Skill | Purpose | State it reads |
|---|---|---|
| `job-scraper` | Find new postings across portals, deduplicate, present matches with fit ratings. Integrates with the `/scrape` workflow. | `job_scraper/seen_jobs.json`, `job_search_tracker.csv` |
| `job-application-assistant` | Evaluate fit against a posting's criteria, tailor a CV, draft a cover letter, prepare interview talking points. | `CLAUDE.md`, `cv/`, `cover_letters/`, `documents/` |
| `upskill` | Compare tracked postings to the profile, produce a gap heatmap and a prioritized learning plan. | `job_search_tracker.csv`, `job_scraper/seen_jobs.json` |

`job-application-assistant` is a bundle: `01-candidate-profile.md`,
`02-behavioral-profile.md`, `03-writing-style.md`, `04-job-evaluation.md`,
`05-cv-templates.md`, `06-cover-letter-templates.md`, `07-interview-prep.md`,
`09-web-research.md`.

### `tools/` — helper scripts

| Script | Role |
|---|---|
| `install_portal_clis.py` | `bun install` in every `.agents/skills/*/cli/` (discovered, not listed). `--dry-run` supported. |
| `job_key.py` | Canonical dedup key for a posting; `--audit` flags pre-rule entries in state. Used by the scrape skill. |
| `rank_state.py` | State helper for the rank flow: selects candidates and writes scores back to `seen_jobs.json`. |
| `robots_check.py` | Decides whether the header-retry in web research may run (honors robots.txt). |
| `verify_pdf.py` | Checks a generated PDF's page count and extractable text layer (ATS check). `--dump-text`, `--contains`. |
| `convert_salary_excel.py` | Converts an Excel salary sheet into `salary_data.json` for `salary_lookup.py`. |
| `README_SALARY_TOOL.md` | Documents the salary-data format. |

### Root scripts

| File | Role |
|---|---|
| `salary_lookup.py` | Salary benchmark lookup from `salary_data.json` (which you supply). Danish spelling-variant and legal-suffix matching. `--city`, `--json`, `--list-all`. |

### Workspace data

| Path | Holds |
|---|---|
| `CLAUDE.md` | The candidate profile. The agent injects this into its system prompt — **fill it in before use**. |
| `cv/` | LaTeX CV variants (`main_example.tex` is the stock moderncv/banking template). |
| `cover_letters/` | `cover.cls`, `cover_example.tex`, and bundled Lato/Raleway fonts under `OpenFonts/`. |
| `documents/` | Career source docs: `cv/`, `linkedin/`, `diplomas/`, `references/`, `projects/`, `postings/`, `applications/`. See `documents/README.md`. |
| `company_research/` | Cache of per-company research used when tailoring applications. |
| `upskill/` | Generated gap heatmaps and learning plans. |
| `job_scraper/` | Dedup state (`seen_jobs.json`). Created on first scrape. |
| `job_search_tracker.csv` | Application tracker: date, company, role, status, fit rating, files, deadlines. |

### `tests/`

`tests/test_agent_tools.py` — 17 unit tests covering skill discovery, the path
guard, CLI argument building per portal, and tool dispatch (read/write/list
roundtrip, error paths). Run with:

```bash
python3 -m unittest discover -s tests -t .
```

### `AGENTS.md`

Pointer file (read by opencode and other agent runtimes) summarizing the layout
and entry points.

---

## How a request flows

1. `python -m agent "<goal>"` starts the loop with the system prompt.
2. The model reads the skill catalog and calls `load_skill` (e.g. `scrape`).
3. It follows the skill's steps, calling `search_jobs` per portal, then
   `job_detail` for promising matches.
4. It reads `job_scraper/seen_jobs.json` (dedup) and `job_search_tracker.csv`,
   then writes new state with `write_file`.
5. For an application, it loads `job-application-assistant`, evaluates fit, drafts
   `cv/main_<company>_<role>.tex` and `cover_letters/cover_<company>_<role>.tex`,
   and records the application under `documents/applications/`.

---

## Adding a portal

1. Drop a new skill under `.agents/skills/<name>/` with a `SKILL.md` and a `cli/`.
2. Register its name, directory, and query/location flags in `PORTALS` in
   `agent/tools.py`.
3. Re-run `python3 tools/install_portal_clis.py`.

The skill's `SKILL.md` frontmatter `description` is what tells the model when to
pick that portal; the `PORTALS` entry is what lets `search_jobs` drive it.
