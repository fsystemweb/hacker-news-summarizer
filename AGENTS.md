# AGENTS.md

Hacker News Summarizer is a Python CLI that fetches the newest Hacker News stories, extracts article text, and prints one-sentence summaries using a Haystack 2.x pipeline and OpenAI.

## Commands
- Install: `python -m venv .venv`, then `pip install -r requirements.txt`
- Run: `python main.py` (help: `python main.py --help`)
- Options: `--last-k` (1 to 20, default 5), `--model`, `--temperature`, `--verbose`, `--json`
- Tests: `pytest` (mocked HN API + CLI; install `-r requirements-dev.txt` too). CI runs them on push/PR. Lint: none configured.

## Conventions
- Stack: Python 3.10+, Haystack (`haystack-ai>=2.24.1`), click, aiohttp, trafilatura, jinja2, python-dotenv. Dependencies are unpinned in `requirements.txt`.
- Structure: `main.py` is the click entry point, `pipeline.py` builds the Pipeline (`create_hn_summarizer_pipeline`), `components/hn_fetcher.py` holds the custom `HackerNewsNewestFetcher` component, `prompts/hn_summary.j2` is the prompt template, `public/` holds the logo.
- Flow: fetcher (async, aiohttp) -> PromptBuilder -> OpenAIGenerator. Stories without an external `url` are skipped.
- Config comes from `.env`; `.env.example` documents `OPENAI_API_KEY`.
- Use type hints and docstrings, as the existing modules do.
- `GEMINI.md` is the original generation prompt for another tool, not a spec for current behavior.

## Boundaries
- Always: re-read `main.py` after editing the click options; the `--json` flag maps to the `as_json` parameter. Do not rename it to `json` or it shadows the `json` module and breaks the `--json` output.
- Ask first: adding a dependency, changing CLI flags or defaults, switching away from OpenAI.
- Ask first: running `python main.py`, since it calls the Hacker News and OpenAI APIs and needs a key.
- Never: commit secrets or read .env files.
