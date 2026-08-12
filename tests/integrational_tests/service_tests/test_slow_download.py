"""
A download that runs out of time is a measurement, not a failure.

The timeout is a controlled observation window: the prober watched for
exactly timeout_seconds and knows how many bytes arrived, which is the
whole point of the service. Only a window that produced nothing at all
counts as the node being unreachable.
"""

import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from src.config import config
from src.entities.probe.enums import ProbeStatus
from src.exc import VideoDownloadError
from src.video_probe.coros import _grade_probe
from src.video_probe.schemas import VideoProbe
from src.video_probe.video_prober import VideoProber


STALL = web.AppKey("stall", asyncio.Event)


def _make_app(first_chunk: bytes) -> web.Application:
    """Serve `first_chunk`, then stall until the client gives up."""

    async def handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(
            status=200,
            headers={"Content-Length": str(64 * 1024 * 1024)},
        )
        await response.prepare(request)

        if first_chunk:
            await response.write(first_chunk)

        await request.app[STALL].wait()
        return response

    app = web.Application()
    app[STALL] = asyncio.Event()
    app.router.add_get("/{tail:.*}", handler)
    return app


@pytest.fixture
async def slow_server():
    servers = []

    async def start(first_chunk: bytes) -> str:
        app = _make_app(first_chunk)
        server = TestServer(app)
        await server.start_server()
        servers.append((server, app))
        return str(server.make_url("/video.mp4"))

    yield start

    for server, app in servers:
        app[STALL].set()
        await server.close()


@pytest.mark.asyncio
class TestTimeoutIsAMeasurement:
    async def test_partial_transfer_returns_a_speed(self, slow_server):
        """The node is alive and serving - just far too slowly."""
        payload = b"x" * 32_768
        url = await slow_server(payload)
        prober = VideoProber(timeout_seconds=2)

        result = await prober._measure_download_speed(url)

        assert result.downloaded_bytes == len(payload)
        assert result.duration_seconds >= 2
        assert result.download_speed_mbps > 0

    async def test_measured_speed_matches_bytes_over_time(self, slow_server):
        payload = b"x" * 65_536
        url = await slow_server(payload)
        prober = VideoProber(timeout_seconds=2)

        result = await prober._measure_download_speed(url)

        expected = result.downloaded_bytes * 8 / result.duration_seconds / 1024 / 1024
        assert result.download_speed_mbps == pytest.approx(expected, abs=0.01)

    async def test_silence_is_still_a_failure(self, slow_server):
        """Nothing ever arrived: that is a dead node, not a slow one."""
        url = await slow_server(b"")
        prober = VideoProber(timeout_seconds=2)

        with pytest.raises(VideoDownloadError) as exc_info:
            await prober._measure_download_speed(url)

        assert "0 bytes" in str(exc_info.value)


class TestCrawlingSpeedIsCritical:
    """The real incident: 1,445,618 bytes in 120.6s is 0.09 Mbps."""

    @staticmethod
    def _probe(speed: float) -> VideoProbe:
        return VideoProbe(
            url="https://example.test/v.mp4",
            size_mb=500.0,
            download_speed_mbps=speed,
            downloaded_bytes=1_445_618,
            download_duration_seconds=120.6,
        )

    def test_crawling_speed_is_critical_with_a_known_bitrate(self):
        status = _grade_probe(self._probe(0.09), bitrate_mbps=8.0, baseline_mbps=50.0)

        assert status is ProbeStatus.CRITICAL

    def test_crawling_speed_is_critical_without_a_bitrate(self):
        """
        A missing bitrate is rare, but it disables the bitrate rule
        entirely, so the floor has to catch this case instead.
        """
        status = _grade_probe(self._probe(0.09), bitrate_mbps=None, baseline_mbps=50.0)

        assert status is ProbeStatus.CRITICAL

    def test_slow_node_is_critical_even_for_a_low_bitrate_video(self):
        """
        A small file must not excuse a slow node.

        Bitrates are mixed across a node: wherever a 480p file lives, a
        1440p file lives too. A node dribbling out the small one - which
        would have arrived instantly in any healthy condition - serves
        the large one at the same rate. Passing it because the bitrate
        rule is satisfied would hide a node failing everything else.
        """
        floor = config.min_baseline_speed_mbps
        speed = floor / 2
        low_bitrate = speed / 4

        # The bitrate rule alone would call this acceptable.
        assert speed >= low_bitrate * 2

        status = _grade_probe(
            self._probe(speed), bitrate_mbps=low_bitrate, baseline_mbps=50.0
        )

        assert status is ProbeStatus.CRITICAL

    def test_healthy_speed_is_unaffected_by_the_floor(self):
        status = _grade_probe(self._probe(80.0), bitrate_mbps=8.0, baseline_mbps=50.0)

        assert status is ProbeStatus.HEALTHY
