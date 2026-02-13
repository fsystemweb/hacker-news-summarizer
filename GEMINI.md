You are a senior AI & backend engineer with deep experience in Haystack 2.x pipelines, LLM integrations, and clean CLI tools.

Current date: February 12, 2026

Task: Build a complete, modern, best-practice Hacker News Summarizer CLI tool using Haystack 2.x and exclusively the OpenAI integration (OpenAIChatGenerator).

Goal of the tool
────────────────
A terminal application that:
1. Fetches the newest K stories from Hacker News via the official Firebase API
2. For stories with a 'url' field: asynchronously downloads & extracts clean main article text (skip Ask HN, jobs, polls, text-only posts without external URL)
3. Creates Haystack Documents with content = extracted text, meta = {title, url, score, descendants (comment count), by (author), time_iso}
4. Builds a Haystack Pipeline that feeds documents into a prompt → generates concise one-sentence summaries using OpenAIChatGenerator
5. Outputs nicely formatted summaries with title, score/comments, one-sentence summary, and URL

Core requirements & modernizations
──────────────────────────────────
• Use Haystack AI ≥ 2.24.1 (latest stable as of Feb 2026)
• Use OpenAIChatGenerator only (from haystack_integrations.components.generators.openai)
• Load OPENAI_API_KEY from .env (via python-dotenv)
• Use click (preferred) or typer for CLI with flags:
  --last-k       (default: 5, int, sensible max 20)
  --model        (OpenAI model name, default: "gpt-5-mini")
  --temperature  (default: 0.3)
  --verbose      (show skipped articles, errors, timings)
  --json         (output machine-readable JSON array instead of pretty text)
• Prefer trafilatura (latest) for article extraction
• Fetch story details & extract content asynchronously (asyncio + aiohttp)
• Gracefully skip: no url, 404, paywall, non-html, parsing failures → log in verbose mode
• Include rich HN metadata in Document.meta
• Strong, concise Jinja2 prompt template → exactly one neutral, informative sentence per post
  Desired output style example:

  1. Show HN: We built X (420 points, 89 comments)
     A next-generation tool that does Y using modern Z architecture.
     https://example.com/very-long-slug

  2. Rust is eating Python alive in 2026 (1050 points, 412 comments)
     New benchmarks show Rust surpassing Python in performance-critical domains...
     https://...

Project structure to generate
─────────────────────────────
project/
├── requirements.txt
├── .env.example
├── README.md               # detailed install, usage, architecture, examples
├── main.py                 # CLI entry point (click)
├── pipeline.py             # factory function → returns ready Haystack Pipeline
├── components/
│   └── hn_fetcher.py       # @component class HackerNewsNewestFetcher (async-compatible)
└── prompts/
    └── hn_summary.j2       # Jinja2 template (or inline if simpler)

Deliverables
────────────
Return the **complete content** of every file above.

Use modern Haystack 2.x style:
- @component
- Pipeline with .add_component() / .connect()
- PromptBuilder + OpenAIChatGenerator
- Documents with content & rich meta
- Optional: pipe.draw("pipeline.png") or pipe.show() suggestions in README

Prompt template guidelines (use doc.meta['title'], doc.content, doc.meta['url'], doc.meta['score'], doc.meta['descendants']):
- Loop over documents
- Instruction: "Provide exactly one concise, neutral, informative sentence summary per post."
- Include title, score/comments in the output formatting instruction

OpenAIChatGenerator example:
from haystack_integrations.components.generators.openai import OpenAIChatGenerator

llm = OpenAIChatGenerator(
    model="gpt-5-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.5
)

Include basic error handling, logging (print in verbose), type hints, docstrings.

Prefer quality, clean code, readability over speed hacks.

Generate the full project files!