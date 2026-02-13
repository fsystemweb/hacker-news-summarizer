import asyncio
import aiohttp
import trafilatura
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from haystack.core.component import component
from haystack.core.serialization import default_from_dict, default_to_dict
from haystack.dataclasses import Document


@component
class HackerNewsNewestFetcher:
    """
    A Haystack component to fetch the newest K stories from Hacker News,
    asynchronously download and extract main article text, and create Haystack Documents.
    """

    def __init__(self, verbose: bool = False):
        """
        Initializes the HackerNewsNewestFetcher.

        :param verbose: If True, prints detailed logs about skipped articles and errors.
        """
        self.hn_api_base = "https://hacker-news.firebaseio.com/v0"
        self.verbose = verbose

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes the component to a dictionary.
        """
        return default_to_dict(self, verbose=self.verbose)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HackerNewsNewestFetcher":
        """
        Deserializes the component from a dictionary.
        """
        return default_from_dict(cls, data)

    async def _fetch_url(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """
        Asynchronously fetches content from a given URL.

        :param session: aiohttp client session.
        :param url: The URL to fetch.
        :return: The text content of the response, or None if an error occurs.
        """
        try:
            async with session.get(url, timeout=10) as response:
                response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
                return await response.text()
        except aiohttp.ClientError as e:
            if self.verbose:
                print(f"DEBUG: Failed to fetch {url}: {e}")
            return None
        except asyncio.TimeoutError:
            if self.verbose:
                print(f"DEBUG: Timeout fetching {url}")
            return None
        except Exception as e:
            if self.verbose:
                print(f"DEBUG: Unexpected error fetching {url}: {e}")
            return None

    async def _extract_article_text(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """
        Asynchronously downloads a webpage and extracts the main article text using trafilatura.

        :param session: aiohttp client session.
        :param url: The URL of the article.
        :return: Extracted text or None if extraction fails.
        """
        html_content = await self._fetch_url(session, url)
        if not html_content:
            return None

        try:
            # download_url can also take content directly
            extracted_text = trafilatura.extract(html_content, include_comments=False, output_format="txt")
            if not extracted_text:
                if self.verbose:
                    print(f"DEBUG: Trafilatura could not extract content from {url}")
                return None
            return extracted_text
        except Exception as e:
            if self.verbose:
                print(f"DEBUG: Error extracting text with trafilatura from {url}: {e}")
            return None

    async def _fetch_story_details(self, session: aiohttp.ClientSession, story_id: int) -> Optional[Dict[str, Any]]:
        """
        Asynchronously fetches details for a single story ID.

        :param session: aiohttp client session.
        :param story_id: The ID of the Hacker News story.
        :return: A dictionary containing story details or None if fetching fails.
        """
        url = f"{self.hn_api_base}/item/{story_id}.json"
        try:
            async with session.get(url, timeout=5) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            if self.verbose:
                print(f"DEBUG: Failed to fetch story details for ID {story_id}: {e}")
            return None
        except asyncio.TimeoutError:
            if self.verbose:
                print(f"DEBUG: Timeout fetching story details for ID {story_id}")
            return None
        except Exception as e:
            if self.verbose:
                print(f"DEBUG: Unexpected error fetching story details for ID {story_id}: {e}")
            return None

    async def _process_story(self, session: aiohttp.ClientSession, story_id: int) -> Optional[Document]:
        """
        Fetches story details, extracts article text (if available), and creates a Document.

        :param session: aiohttp client session.
        :param story_id: The ID of the Hacker News story.
        :return: A Haystack Document or None if the story is skipped or processing fails.
        """
        details = await self._fetch_story_details(session, story_id)
        if not details or details.get("type") != "story":
            if self.verbose:
                print(f"SKIPPED: ID {story_id} (not a story or details missing)")
            return None

        # Skip Ask HN, jobs, polls, text-only posts without external URL
        if "url" not in details or not details["url"]:
            if self.verbose:
                print(f"SKIPPED: '{details.get('title', 'N/A')}' (ID: {story_id}) - No external URL")
            return None

        # Convert Unix timestamp to ISO 8601 string
        time_iso = datetime.fromtimestamp(details["time"], tz=timezone.utc).isoformat() if "time" in details else None

        article_text = await self._extract_article_text(session, details["url"])

        if not article_text:
            if self.verbose:
                print(f"SKIPPED: '{details.get('title', 'N/A')}' (ID: {story_id}) - Could not extract article text or content was empty")
            return None

        # Create Haystack Document
        metadata = {
            "title": details.get("title"),
            "url": details["url"],
            "score": details.get("score", 0),
            "descendants": details.get("descendants", 0),  # comment count
            "by": details.get("by"),
            "time_iso": time_iso,
            "id": story_id,
        }
        return Document(content=article_text, meta=metadata)

    async def _run_async(self, last_k: int = 5):
        """
        Internal async method to fetch and process stories.

        :param last_k: The number of newest stories to fetch.
        :return: A dictionary containing a list of Haystack Documents.
        """
        async with aiohttp.ClientSession() as session:
            try:
                # Fetch top story IDs
                top_stories_url = f"{self.hn_api_base}/newstories.json"
                async with session.get(top_stories_url, timeout=5) as response:
                    response.raise_for_status()
                    top_story_ids = await response.json()
            except aiohttp.ClientError as e:
                if self.verbose:
                    print(f"ERROR: Failed to fetch top story IDs: {e}")
                return {"documents": []}
            except asyncio.TimeoutError:
                if self.verbose:
                    print("ERROR: Timeout fetching top story IDs.")
                return {"documents": []}
            except Exception as e:
                if self.verbose:
                    print(f"ERROR: Unexpected error fetching top story IDs: {e}")
                return {"documents": []}

            # Limit to last_k stories and create tasks for parallel processing
            story_ids_to_process = top_story_ids[:last_k]
            tasks = [self._process_story(session, story_id) for story_id in story_ids_to_process]

            # Run tasks concurrently
            processed_documents = await asyncio.gather(*tasks)

            # Filter out None values (skipped stories)
            documents = [doc for doc in processed_documents if doc is not None]

            if self.verbose:
                print(f"Finished fetching. Processed {len(documents)} out of {last_k} requested stories.")

            return {"documents": documents}

    @component.output_types(documents=List[Document])
    def run(self, last_k: int = 5):
        """
        Runs the Hacker News fetcher to retrieve and process stories.

        :param last_k: The number of newest stories to fetch.
        :return: A dictionary containing a list of Haystack Documents.
        """
        return asyncio.run(self._run_async(last_k))
