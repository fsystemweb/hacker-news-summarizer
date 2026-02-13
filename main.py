import asyncio
import os
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, List

import click
from dotenv import load_dotenv

from pipeline import create_hn_summarizer_pipeline

# Load environment variables from .env file
load_dotenv()

@click.command()
@click.option(
    "--last-k",
    default=5,
    type=click.IntRange(1, 20),
    help="Number of newest Hacker News stories to fetch (max 20).",
    show_default=True,
)
@click.option(
    "--model",
    default="gpt-5.2",
    type=str,
    help="OpenAI model name to use for summarization.",
    show_default=True,
)
@click.option(
    "--temperature",
    default=0.5,
    type=float,
    help="Temperature for the OpenAI model (0.0 to 1.0).",
    show_default=True,
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show skipped articles, errors, and timings.",
)
@click.option(
    "--json",
    is_flag=True,
    help="Output machine-readable JSON array instead of pretty text.",
)
def main(last_k: int, model: str, temperature: float, verbose: bool, json: bool):
    """
    Hacker News Summarizer CLI: Fetches the newest K stories, extracts article text,
    and generates concise one-sentence summaries using Haystack 2.x and OpenAI.
    """
    if verbose:
        click.echo(f"🚀 Starting Hacker News Summarizer (verbose mode enabled)")
        click.echo(f"Parameters: last_k={last_k}, model='{model}', temperature={temperature}")

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        click.echo(
            click.style(
                "Error: OPENAI_API_KEY environment variable not set. "
                "Please create a .env file or set the variable.",
                fg="red",
            ),
            err=True,
        )
        raise click.Abort()

    start_time = time.monotonic()

    # Create the Haystack pipeline
    pipeline = create_hn_summarizer_pipeline(openai_api_key, model, temperature, verbose)

    try:
        # Run the pipeline
        if verbose:
            click.echo("Fetching and processing Hacker News stories...")
        result = pipeline.run(data={"hn_fetcher": {"last_k": last_k}})

    except Exception as e:
        click.echo(
            click.style(f"An error occurred during pipeline execution: {e}", fg="red"),
            err=True,
        )
        raise click.Abort()

    summaries: List[Dict[str, Any]] = []
    # Extract results and format them
    if "document_processor" in result and "results" in result["document_processor"]:
        for item in result["document_processor"]["results"]:
            document = item.get("document")
            summary_text = item.get("summary", "N/A")

            # Ensure 'document.meta' exists and contains necessary keys
            title = document.meta.get("title", "N/A")
            url = document.meta.get("url", "N/A")
            score = document.meta.get("score", 0)
            comments = document.meta.get("descendants", 0)
            time_iso = document.meta.get("time_iso", "N/A")
            by = document.meta.get("by", "N/A")

            summaries.append(
                {
                    "title": title,
                    "url": url,
                    "score": score,
                    "comments": comments,
                    "summary": summary_text,
                    "time_iso": time_iso,
                    "by": by,
                }
            )

    end_time = time.monotonic()
    duration = end_time - start_time

    if verbose:
        click.echo(f"Total execution time: {duration:.2f} seconds")

    if json:
        click.echo(json.dumps(summaries, indent=2))
    else:
        if summaries:
            click.echo()
            click.echo(click.style("━━━ Hacker News Summaries ━━━", fg="cyan", bold=True))
            click.echo()
            
            for i, item in enumerate(summaries, 1):
                # Post number and title
                click.echo(click.style(f"{i}. {item['title']}", fg='bright_green', bold=True))
                
                # Score and comments
                click.echo(click.style(f"   ({item['score']} points, {item['comments']} comments)", fg='bright_yellow'))
                
                # Summary text
                click.echo(f"   {item['summary']}")
                
                # URL
                click.echo(click.style(f"   {item['url']}", fg='bright_blue', underline=True))
                
                # Separator between posts (except after the last one)
                if i < len(summaries):
                    click.echo()
                    click.echo(click.style("─" * 70, fg='bright_black'))
                    click.echo()
            
            click.echo()
            click.echo(click.style("━━━━━━━━━━━━━━━━━━━━━━━━━━━━", fg="cyan", bold=True))
        else:
            click.echo(click.style("No summaries generated. Try increasing --last-k or check verbose output for skipped articles.", fg="yellow"))


if __name__ == "__main__":
    main()
