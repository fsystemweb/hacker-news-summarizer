"""CLI-level tests for main.py using click's CliRunner and a stubbed pipeline.

These tests cover the ``--json`` flag (previously broken by the parameter
shadowing the ``json`` module) without calling the Hacker News or OpenAI APIs.
"""

import json
from types import SimpleNamespace

from click.testing import CliRunner

import main
from main import main as cli


def stub_document(**meta):
    return SimpleNamespace(meta=meta)


def stub_result():
    return {
        "document_processor": {
            "results": [
                {
                    "document": stub_document(
                        title="Stubbed title",
                        url="https://example.com/stub",
                        score=42,
                        descendants=7,
                        time_iso="2024-01-01T00:00:00+00:00",
                        by="tester",
                    ),
                    "summary": "One-line stubbed summary.",
                }
            ]
        }
    }


class StubPipeline:
    """Drop-in replacement for the real Haystack pipeline."""

    def __init__(self, result=None):
        self.result = result if result is not None else stub_result()

    def run(self, data):
        return self.result


def invoke_cli(monkeypatch, args, pipeline=None):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main, "create_hn_summarizer_pipeline", lambda *a, **kw: pipeline or StubPipeline())
    runner = CliRunner()
    return runner.invoke(cli, args)


class TestJsonFlag:
    def test_json_flag_emits_parsable_json(self, monkeypatch):
        result = invoke_cli(monkeypatch, ["--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert payload == [
            {
                "title": "Stubbed title",
                "url": "https://example.com/stub",
                "score": 42,
                "comments": 7,
                "summary": "One-line stubbed summary.",
                "time_iso": "2024-01-01T00:00:00+00:00",
                "by": "tester",
            }
        ]

    def test_json_flag_with_no_summaries(self, monkeypatch):
        empty_pipeline = StubPipeline(result={"document_processor": {"results": []}})
        result = invoke_cli(monkeypatch, ["--json"], pipeline=empty_pipeline)

        assert result.exit_code == 0
        assert json.loads(result.output) == []


class TestPrettyOutput:
    def test_default_pretty_output(self, monkeypatch):
        result = invoke_cli(monkeypatch, [])

        assert result.exit_code == 0
        assert "Hacker News Summaries" in result.output
        assert "Stubbed title" in result.output
        assert "One-line stubbed summary." in result.output

    def test_no_summaries_message(self, monkeypatch):
        empty_pipeline = StubPipeline(result={"document_processor": {"results": []}})
        result = invoke_cli(monkeypatch, [], pipeline=empty_pipeline)

        assert result.exit_code == 0
        assert "No summaries generated" in result.output


class TestErrors:
    def test_missing_api_key_aborts(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code != 0
        assert "OPENAI_API_KEY" in result.output
