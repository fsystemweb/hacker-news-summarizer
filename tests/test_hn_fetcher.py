"""Unit tests for the HackerNewsNewestFetcher component.

The Hacker News Firebase API is mocked with a local ``aiohttp`` test server.
No network access and no OpenAI credentials are required.
"""

import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from components.hn_fetcher import HackerNewsNewestFetcher


class Delayed:
    """Serves ``value`` (a plain JSON payload or a ``Raw`` response) after ``delay`` seconds."""

    def __init__(self, delay: float, value=None):
        self.delay = delay
        self.value = value


class Raw:
    """Serves an arbitrary status/body without JSON encoding."""

    def __init__(self, status: int, body: bytes, content_type: str = "text/plain"):
        self.status = status
        self.body = body
        self.content_type = content_type


class HNMock:
    """A tiny in-memory fake of the Hacker News Firebase API plus article pages.

    Serves:
      - GET /v0/newstories.json        -> ``self.newstories``
      - GET /v0/item/{story_id}.json   -> ``self.items[story_id]``
      - GET /articles/{story_id}       -> ``self.articles[story_id]``

    Any stored value may be wrapped in ``Delayed`` or be a ``Raw`` response to
    simulate latency or malformed/unavailable endpoints.
    """

    def __init__(self):
        self.newstories = []
        self.items = {}
        self.articles = {}

    def app(self) -> web.Application:
        application = web.Application()
        application.router.add_get("/v0/newstories.json", self._newstories)
        application.router.add_get(r"/v0/item/{story_id:\d+}.json", self._item)
        application.router.add_get(r"/articles/{story_id:\d+}", self._article)
        return application

    def url(self, server: TestServer, path: str) -> str:
        """Absolute URL for a mocked article page served by ``server``."""
        return str(server.make_url(path))

    async def _respond(self, value):
        if isinstance(value, Delayed):
            await asyncio.sleep(value.delay)
            value = value.value
        if isinstance(value, Raw):
            return web.Response(status=value.status, body=value.body, content_type=value.content_type)
        if isinstance(value, bytes):
            return web.Response(body=value, content_type="text/html")
        return web.json_response(value)

    async def _newstories(self, request):
        return await self._respond(self.newstories)

    async def _item(self, request):
        story_id = int(request.match_info["story_id"])
        return await self._respond(self.items.get(story_id))

    async def _article(self, request):
        story_id = int(request.match_info["story_id"])
        return await self._respond(self.articles.get(story_id))


def story(story_id: int, url=None, **overrides) -> dict:
    """Build a valid HN story item payload."""
    payload = {
        "id": story_id,
        "type": "story",
        "title": f"Story {story_id}",
        "url": url,
        "score": 100 + story_id,
        "descendants": 10 + story_id,
        "by": "tester",
        "time": 1700000000 + story_id,
    }
    payload.update(overrides)
    return payload


def article_html(story_id: int) -> bytes:
    return f"<html><body><article>Full article text for story {story_id}.</article></body></html>".encode()


@pytest_asyncio.fixture
async def hn_mock():
    mock = HNMock()
    server = TestServer(mock.app())
    await server.start_server()
    try:
        yield mock, server
    finally:
        await server.close()


async def run_fetcher(mock, server, fetcher=None, last_k=5):
    fetcher = fetcher or HackerNewsNewestFetcher(verbose=False)
    # Point the component at the local mock instead of the real Firebase API.
    fetcher.hn_api_base = str(server.make_url("/v0"))
    return await fetcher._run_async(last_k=last_k)


class TestHappyPath:
    async def test_produces_documents_with_metadata(self, hn_mock):
        mock, server = hn_mock

        article_url = mock.url(server, "/articles/1")
        mock.newstories = [1, 2, 3]
        mock.items = {
            1: story(1, url=article_url),
            2: story(2, by="someone"),  # no external URL -> skipped
            3: story(3, type="job", url=article_url, title="Show HN: Job"),  # wrong type -> skipped
        }
        mock.articles = {1: article_html(1)}

        result = await run_fetcher(mock, server, last_k=3)

        docs = result["documents"]
        assert len(docs) == 1
        doc = docs[0]
        assert doc.content == "Full article text for story 1."
        assert doc.meta["title"] == "Story 1"
        assert doc.meta["url"] == article_url
        assert doc.meta["score"] == 101
        assert doc.meta["descendants"] == 11
        assert doc.meta["by"] == "tester"
        assert doc.meta["id"] == 1
        assert doc.meta["time_iso"] == datetime.fromtimestamp(1700000001, tz=timezone.utc).isoformat()

    async def test_takes_last_k_from_newstories(self, hn_mock):
        mock, server = hn_mock
        mock.newstories = [1, 2, 3, 4, 5]
        for i in range(1, 6):
            mock.items[i] = story(i, url=mock.url(server, f"/articles/{i}"))
            mock.articles[i] = article_html(i)

        result = await run_fetcher(mock, server, last_k=2)
        assert len(result["documents"]) == 2


class TestEmptyResults:
    async def test_no_newstories_returns_empty(self, hn_mock):
        mock, server = hn_mock
        mock.newstories = []
        result = await run_fetcher(mock, server)
        assert result == {"documents": []}

    async def test_all_stories_skipped_returns_empty(self, hn_mock):
        mock, server = hn_mock
        mock.newstories = [1, 2]
        mock.items = {1: None, 2: None}  # details missing -> skipped
        result = await run_fetcher(mock, server)
        assert result == {"documents": []}

    async def test_article_text_extraction_failure_skips_story(self, hn_mock):
        mock, server = hn_mock
        mock.newstories = [1]
        # Article page returns empty body -> trafilatura cannot extract text.
        mock.items = {1: story(1, url=mock.url(server, "/articles/1"))}
        mock.articles = {1: Raw(status=200, body=b"<html><body><p></p></body></html>")}
        result = await run_fetcher(mock, server)
        assert result == {"documents": []}


class TestMalformedResponses:
    async def test_non_json_item_body_is_skipped(self, hn_mock):
        mock, server = hn_mock
        mock.newstories = [1]
        mock.items = {1: Raw(status=200, body=b"<!DOCTYPE html>Service unavailable")}
        result = await run_fetcher(mock, server)
        assert result == {"documents": []}

    async def test_http_error_status_is_skipped(self, hn_mock):
        mock, server = hn_mock
        mock.newstories = [1, 2]
        mock.items = {1: Raw(status=500, body=b"boom"), 2: Raw(status=404, body=b"nope")}
        result = await run_fetcher(mock, server)
        assert result == {"documents": []}


class TestTimeouts:
    async def test_slow_story_details_are_skipped(self, hn_mock):
        mock, server = hn_mock
        mock.newstories = [1]
        mock.items = {1: Delayed(delay=1.0)}
        fetcher = HackerNewsNewestFetcher(verbose=False, story_fetch_timeout=0.2)
        result = await run_fetcher(mock, server, fetcher=fetcher)
        assert result == {"documents": []}

    async def test_slow_newstories_returns_empty(self, hn_mock):
        mock, server = hn_mock
        mock.newstories = Delayed(delay=1.0, value=[1])
        fetcher = HackerNewsNewestFetcher(verbose=False, story_fetch_timeout=0.2)
        result = await run_fetcher(mock, server, fetcher=fetcher)
        assert result == {"documents": []}

    async def test_slow_article_page_is_skipped(self, hn_mock):
        mock, server = hn_mock
        mock.newstories = [1]
        mock.items = {1: story(1, url=mock.url(server, "/articles/1"))}
        mock.articles = {1: Delayed(delay=1.0, value=article_html(1))}
        fetcher = HackerNewsNewestFetcher(verbose=False, article_fetch_timeout=0.2)
        result = await run_fetcher(mock, server, fetcher=fetcher)
        assert result == {"documents": []}


class TestSerialization:
    def test_to_dict_round_trip(self):
        fetcher = HackerNewsNewestFetcher(verbose=True, article_fetch_timeout=7, story_fetch_timeout=3)
        data = fetcher.to_dict()

        assert data["init_parameters"]["verbose"] is True
        assert data["init_parameters"]["article_fetch_timeout"] == 7
        assert data["init_parameters"]["story_fetch_timeout"] == 3

        restored = HackerNewsNewestFetcher.from_dict(data)
        assert isinstance(restored, HackerNewsNewestFetcher)
        assert restored.verbose is True
        assert restored.article_fetch_timeout == 7
        assert restored.story_fetch_timeout == 3

    def test_from_dict_backward_compatible(self):
        data = {"type": "components.hn_fetcher.HackerNewsNewestFetcher", "init_parameters": {"verbose": True}}
        restored = HackerNewsNewestFetcher.from_dict(data)
        assert restored.verbose is True
        assert restored.article_fetch_timeout == 10.0  # new defaults apply to old payloads
        assert restored.story_fetch_timeout == 5.0
