"""
The loader fills storage probe pools from the KVS API catalog.

The API cannot filter by storage, so the loader walks the whole catalog
and matches videos to storages by server group, stopping as soon as
every free slot is filled.
"""

from contextlib import asynccontextmanager

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from sqlalchemy import select, update
from tenacity import wait_none

from src.config import config
from src.entities.storage.model import Storage
from src.entities.storage.services import StorageService
from src.entities.video.model import Video
from src.video_probe import coros, video_loader as video_loader_module
from src.video_probe.schemas import KVSVideo
from src.video_probe.video_loader import VideoLoader, pick_video_format

MB = 1024 * 1024


def _variant(suffix: str, dimensions: str, size_bytes: int | str) -> str:
    """Build one `file_formats` chunk the way KVS stores it."""
    return f"||{suffix}|{dimensions}|600|{size_bytes}|0|0|0|0|0|h264|30"


FORMATS_1080 = (
    _variant("_preview.mp4", "608x342", 1 * MB)
    + _variant("_720p.mp4", "1280x720", 400 * MB)
    + _variant("_1080p.mp4", "1920x1080", 900 * MB)
)

RECORDS = [
    {"video_id": 1, "server_group_id": 3, "file_formats": FORMATS_1080},
    {
        "video_id": 2,
        "server_group_id": 3,
        "file_formats": _variant("_1080p.mp4", "1920x1080", 50 * MB),
    },
    {"video_id": 3, "server_group_id": 4, "file_formats": FORMATS_1080},
    {"video_id": 4, "server_group_id": 3, "file_formats": FORMATS_1080},
    {"video_id": 5, "server_group_id": 4, "file_formats": FORMATS_1080},
]

REQUESTS = web.AppKey("requests", list)
FAILURES = web.AppKey("failures", list)


def _make_app(
    records: list[dict], failures: list[int] | None = None
) -> web.Application:
    """Serve `records` the way /videos/all-simple does."""

    async def handler(request: web.Request) -> web.Response:
        request.app[REQUESTS].append(dict(request.query))

        if request.app[FAILURES]:
            return web.Response(status=request.app[FAILURES].pop(0))

        limit = int(request.query["limit"])
        id_gt = int(request.query.get("id_gt", 0))
        page = [r for r in records if r["video_id"] > id_gt][:limit]

        if not page:
            return web.json_response({"detail": "VIDEO_NOT_FOUND"}, status=404)
        return web.json_response(page)

    app = web.Application()
    app[REQUESTS] = []
    app[FAILURES] = list(failures or [])
    app.router.add_get("/videos/all-simple", handler)
    return app


@pytest.fixture
async def kvs_api(monkeypatch):
    servers = []

    async def start(
        records: list[dict], failures: list[int] | None = None
    ) -> tuple[VideoLoader, web.Application]:
        app = _make_app(records, failures)
        server = TestServer(app)
        await server.start_server()
        servers.append(server)
        monkeypatch.setattr(config, "pb_kvs_api_endpoint", str(server.make_url("/")))
        return VideoLoader(), app

    monkeypatch.setattr(config, "video_min_size_mb", 100)
    monkeypatch.setattr(video_loader_module, "PAGE_LIMIT", 2)
    monkeypatch.setattr(VideoLoader._fetch_page.retry, "wait", wait_none())

    yield start

    for server in servers:
        await server.close()


async def _collect(loader: VideoLoader) -> list[KVSVideo]:
    return [video async for page in loader.iter_pages() for video in page]


class TestPickVideoFormat:
    @pytest.fixture(autouse=True)
    def min_size(self, monkeypatch):
        monkeypatch.setattr(config, "video_min_size_mb", 100)

    def test_picks_tallest_variant(self):
        assert pick_video_format(FORMATS_1080) == "_1080p.mp4"

    def test_real_kvs_value(self):
        formats = (
            "||_360p.mp4|640x360|3997|363110475|0|0|0|0|0|h264|30"
            "||.mp4|852x480|3997|514344326|0|0|0|0|0|h264|30"
            "||_2160p.mp4|3840x2160|3997|8459579159|0|0|0|0|0|h264|30"
            "||_preview.mp4|608x342|8|535718|0|0|0|0|0|h264|60"
            "||_source.mkv|3840x2160|3997|12141235773|0|0|0|0|0|h264|30"
        )

        assert pick_video_format(formats) == "_2160p.mp4"

    def test_prefers_mp4_without_pb_prefix(self):
        formats = (
            _variant("_pb_1080p.mp4", "1920x1080", 900 * MB)
            + _variant("_1080p.webm", "1920x1080", 900 * MB)
            + _variant("_1080p.mp4", "1920x1080", 900 * MB)
        )

        assert pick_video_format(formats) == "_1080p.mp4"

    def test_never_picks_source_of_vertical_video(self):
        formats = (
            _variant("_1080p.mp4", "606x1080", 170 * MB)
            + _variant("_source.mkv", "1080x1920", 570 * MB)
            + _variant("_pb_source.mkv", "2160x3840", 1000 * MB)
        )

        assert pick_video_format(formats) == "_1080p.mp4"

    def test_skips_variants_below_min_size(self):
        formats = _variant("_720p.mp4", "1280x720", 150 * MB) + _variant(
            "_1080p.mp4", "1920x1080", 99 * MB
        )

        assert pick_video_format(formats) == "_720p.mp4"

    def test_video_too_small_everywhere(self):
        formats = (
            _variant("_720p.mp4", "1280x720", 40 * MB)
            + _variant("_1080p.mp4", "1920x1080", 99 * MB)
            + _variant("_source.mkv", "1920x1080", 500 * MB)
        )

        assert pick_video_format(formats) is None

    def test_ignores_malformed_chunks(self):
        formats = (
            "||_broken.mp4|1920x1080"
            + _variant("_x.mp4", "axb", 900 * MB)
            + _variant("_1080p.mp4", "1920x1080", "N/A")
        )

        assert pick_video_format(formats) is None

    def test_empty(self):
        assert pick_video_format("") is None


@pytest.mark.asyncio
class TestVideoLoader:
    async def test_walks_every_page(self, kvs_api):
        loader, app = await kvs_api(RECORDS)

        videos = await _collect(loader)

        assert [v.kvs_id for v in videos] == [1, 3, 4, 5]
        assert [q.get("id_gt") for q in app[REQUESTS]] == [None, "2", "4"]
        assert all(q["status_id"] == "1" for q in app[REQUESTS])
        assert "is_vertical" not in app[REQUESTS][0]

    async def test_stops_on_short_page_without_extra_request(self, kvs_api):
        loader, app = await kvs_api(RECORDS[:3])

        await _collect(loader)

        assert len(app[REQUESTS]) == 2

    async def test_empty_catalog(self, kvs_api):
        loader, _ = await kvs_api([])

        assert await _collect(loader) == []

    async def test_genuine_404_is_an_error(self, kvs_api):
        loader, _ = await kvs_api(RECORDS)
        loader._url += "-wrong"

        with pytest.raises(aiohttp.ClientResponseError):
            await _collect(loader)

    async def test_retries_server_errors(self, kvs_api):
        loader, app = await kvs_api(RECORDS[:1], failures=[503])

        videos = await _collect(loader)

        assert [v.kvs_id for v in videos] == [1]
        assert len(app[REQUESTS]) == 2

    async def test_does_not_retry_client_errors(self, kvs_api):
        loader, app = await kvs_api(RECORDS, failures=[401])

        with pytest.raises(aiohttp.ClientResponseError):
            await _collect(loader)

        assert len(app[REQUESTS]) == 1


@pytest.mark.asyncio
class TestLoadVideos:
    @pytest.fixture(autouse=True)
    async def setup(self, async_session, kvs_api, monkeypatch):
        @asynccontextmanager
        async def get_session():
            yield async_session

        monkeypatch.setattr(coros, "get_session", get_session)
        monkeypatch.setattr(config, "probes_per_storage", 2)

        # Mocked storages 1 and 2 get server groups 3 and 4. Storage 1
        # holds one good video, storage 2 holds none.
        await async_session.execute(update(Storage).values(server_group_id=None))
        await async_session.execute(
            update(Storage).where(Storage.id == 1).values(server_group_id=3)
        )
        await async_session.execute(
            update(Storage).where(Storage.id == 2).values(server_group_id=4)
        )
        await async_session.execute(
            update(Video).where(Video.storage_id == 2).values(is_bad=True)
        )
        await async_session.commit()

        self.session = async_session
        self.kvs_api = kvs_api
        self.monkeypatch = monkeypatch

    async def _videos_of(self, storage_id: int) -> set[int]:
        result = await self.session.execute(
            select(Video.kvs_id).where(
                Video.storage_id == storage_id, Video.is_bad.is_(False)
            )
        )
        return set(result.scalars().all())

    async def _start(self, records: list[dict]) -> web.Application:
        loader, app = await self.kvs_api(records)
        self.monkeypatch.setattr(coros, "video_loader", loader)
        return app

    async def test_slots(self):
        service = StorageService(self.session)

        slots = {s.storage_id: s.free_slots for s in await service.get_slots()}

        assert slots == {1: 1, 2: 2}

    async def test_fills_free_slots_per_storage(self):
        before = await self._videos_of(1)
        await self._start(RECORDS)

        await coros.load_videos()

        assert await self._videos_of(1) == before | {1}
        assert await self._videos_of(2) == {3, 5}

    async def test_stops_requesting_once_every_slot_is_filled(self):
        records = RECORDS + [
            {"video_id": 6, "server_group_id": 4, "file_formats": FORMATS_1080},
        ]
        app = await self._start(records)

        await coros.load_videos()

        assert len(app[REQUESTS]) == 3
        assert await self._videos_of(2) == {3, 5}

    async def test_skips_known_videos(self):
        await self.session.execute(
            update(Video).where(Video.storage_id == 2).values(kvs_id=3)
        )
        await self.session.commit()
        await self._start(RECORDS)

        await coros.load_videos()

        assert await self._videos_of(2) == {5}

    async def test_skips_unknown_server_groups(self):
        await self._start(
            [{"video_id": 7, "server_group_id": 99, "file_formats": FORMATS_1080}]
        )

        await coros.load_videos()

        result = await self.session.execute(select(Video).where(Video.kvs_id == 7))
        assert result.scalar_one_or_none() is None

    async def test_full_pools_skip_the_api(self):
        await self.session.execute(update(Storage).values(server_group_id=None))
        await self.session.commit()
        app = await self._start(RECORDS)

        await coros.load_videos()

        assert app[REQUESTS] == []
