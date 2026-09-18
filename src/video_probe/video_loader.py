from collections.abc import AsyncIterator
from typing import Any, Final

import aiohttp
from loguru import logger
from pydantic import ValidationError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.config import config
from src.exc import KVSAPIError
from src.video_probe.schemas import KVSVideo

VIDEOS_PATH: Final[str] = "/videos/all-simple"
PAGE_LIMIT: Final[int] = 1000
ACTIVE_STATUS_ID: Final[int] = 1
REQUEST_TIMEOUT_SECONDS: Final[int] = 60
RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})

# The API answers an empty page with this 404 instead of an empty list.
END_OF_LIST_DETAIL: Final[str] = "VIDEO_NOT_FOUND"


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, aiohttp.ClientConnectionError | TimeoutError):
        return True
    return (
        isinstance(exc, aiohttp.ClientResponseError)
        and exc.status in RETRYABLE_STATUS_CODES
    )


def _variant_rank(variant: tuple[int, str]) -> tuple[int, bool, bool]:
    height, suffix = variant
    return height, suffix.endswith(".mp4"), not suffix.startswith("_pb_")


def _parse_variant(chunk: str) -> tuple[int, str] | None:
    fields = chunk.split("|")
    if len(fields) < 2 or "preview" in fields[0]:
        return None
    height = fields[1].partition("x")[2]
    if not height.isdigit():
        return None
    return int(height), fields[0]


def pick_video_format(file_formats: str) -> str | None:
    """
    Pick the format suffix of the best variant a KVS video has.

    `file_formats` lists the variants as `||`-separated chunks of
    `suffix|WIDTHxHEIGHT|...`. The tallest variant wins, since the prober
    rejects small files; among equals an .mp4 without the `_pb_` prefix
    is preferred. Previews are never picked.

    Args:
        file_formats: Raw `file_formats` value from the KVS API.

    Returns:
        str | None: Format suffix (e.g. "_1080p.mp4"), or None if the
            video has no usable variant.
    """
    variants = [
        variant
        for chunk in file_formats.split("||")
        if chunk and (variant := _parse_variant(chunk))
    ]
    if not variants:
        return None
    return max(variants, key=_variant_rank)[1]


class VideoLoader:
    """
    Client for listing PB videos through the KVS API plugin.

    The API offers a single paginated listing of every video, ordered by
    video_id, and knows nothing about storages. Pages are walked with the
    `id_gt` keyset cursor rather than an offset, which stays cheap deep
    into the catalog.
    """

    def __init__(self) -> None:
        self._url = config.pb_kvs_api_endpoint.rstrip("/") + VIDEOS_PATH
        self._auth = aiohttp.BasicAuth(
            config.pb_kvs_api_user,
            config.pb_kvs_api_password.get_secret_value(),
        )

    async def iter_pages(self) -> AsyncIterator[list[KVSVideo]]:
        """
        Walk every active video in the catalog, a page at a time.

        Yields:
            list[KVSVideo]: Videos of one page that have a usable format.

        Raises:
            KVSAPIError: If the API returns something other than a list.
            aiohttp.ClientError: If a request fails after all retries.
        """
        id_gt: int | None = None

        while True:
            records = await self._fetch_page(id_gt)
            if not records:
                return

            yield self._parse_page(records)

            if len(records) < PAGE_LIMIT:
                return

            id_gt = records[-1]["video_id"]

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=1, max=30),
        reraise=True,
    )
    async def _fetch_page(self, id_gt: int | None) -> list[dict[str, Any]]:
        """
        Fetch one raw page of the video listing.

        Args:
            id_gt: Return only videos with a greater video_id.

        Returns:
            list[dict[str, Any]]: Raw video records, empty past the end.

        Raises:
            KVSAPIError: If the API returns something other than a list.
            aiohttp.ClientResponseError: For any other error status.
        """
        params = {"limit": PAGE_LIMIT, "status_id": ACTIVE_STATUS_ID}
        if id_gt is not None:
            params["id_gt"] = id_gt

        async with aiohttp.ClientSession(
            auth=self._auth,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
        ) as session:
            async with session.get(self._url, params=params) as response:
                if await self._is_end_of_list(response):
                    return []

                response.raise_for_status()
                data = await response.json()

        if not isinstance(data, list):
            raise KVSAPIError(
                f"KVS API returned {type(data).__name__} instead of a list "
                f"for {self._url}: {str(data)[:300]}"
            )
        return data

    @staticmethod
    async def _is_end_of_list(response: aiohttp.ClientResponse) -> bool:
        """
        Tell the API's empty-page 404 apart from a genuine 404.

        A wrong URL answers 404 too, and treating it as the end of the
        catalog would silently load nothing.

        Args:
            response: Response to inspect.

        Returns:
            bool: True if the listing simply has no more videos.
        """
        if response.status != 404:
            return False

        try:
            body = await response.json()
        except (aiohttp.ContentTypeError, ValueError):
            return False

        return isinstance(body, dict) and body.get("detail") == END_OF_LIST_DETAIL

    @staticmethod
    def _parse_page(records: list[dict[str, Any]]) -> list[KVSVideo]:
        """
        Turn raw records into videos, skipping those that cannot be probed.

        Args:
            records: Raw video records.

        Returns:
            list[KVSVideo]: Videos with a usable format.
        """
        videos: list[KVSVideo] = []

        for record in records:
            video_format = pick_video_format(record.get("file_formats") or "")
            if video_format is None:
                continue

            try:
                videos.append(
                    KVSVideo.model_validate(
                        {
                            "kvs_id": record.get("video_id"),
                            "server_group_id": record.get("server_group_id"),
                            "video_format": video_format,
                        }
                    )
                )
            except ValidationError as exc:
                logger.warning(
                    f"Skipping invalid KVS video "
                    f"video_id={record.get('video_id')!r}: {exc}"
                )

        return videos


video_loader = VideoLoader()
