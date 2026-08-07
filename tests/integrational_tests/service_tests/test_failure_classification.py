import pytest

from src.entities.probe.enums import ProbeFailureReason
from src.video_probe.video_prober import VideoProber

CLOUDFLARE_HEADERS = {
    "Server": "cloudflare",
    "CF-RAY": "a2774892bc5cfc19-DUS",
    "Content-Disposition": 'inline; filename="569344_1440p.mp4"',
}

STORAGE_NODE_HEADERS = {
    "Server": "nginx",
    "Content-Disposition": 'inline; filename="94e5ebe084b8f91998fc52b8daa27f9230b8e1ee.mp4"',
}


class TestFailureClassification:
    def test_node_404_is_missing_on_node(self):
        reason = VideoProber._classify_failure(404, STORAGE_NODE_HEADERS)

        assert reason is ProbeFailureReason.FILE_MISSING_ON_NODE

    def test_cloudflare_404_is_missing_in_catalog(self):
        reason = VideoProber._classify_failure(404, CLOUDFLARE_HEADERS)

        assert reason is ProbeFailureReason.FILE_MISSING_IN_CATALOG

    def test_404_without_headers_falls_back_to_catalog(self):
        reason = VideoProber._classify_failure(404)

        assert reason is ProbeFailureReason.FILE_MISSING_IN_CATALOG

    @pytest.mark.parametrize(
        "status, expected",
        [
            (403, ProbeFailureReason.LINK_REJECTED),
            (410, ProbeFailureReason.IP_BLOCKED),
            (429, ProbeFailureReason.RATE_LIMITED),
            (500, ProbeFailureReason.STORAGE_ERROR),
            (503, ProbeFailureReason.STORAGE_ERROR),
            (521, ProbeFailureReason.ORIGIN_UNREACHABLE),
            (522, ProbeFailureReason.ORIGIN_UNREACHABLE),
            (525, ProbeFailureReason.ORIGIN_TLS_ERROR),
            (526, ProbeFailureReason.ORIGIN_TLS_ERROR),
            (527, ProbeFailureReason.ORIGIN_UNREACHABLE),
            (530, ProbeFailureReason.STORAGE_ERROR),
            (418, ProbeFailureReason.UNKNOWN),
            (None, ProbeFailureReason.STORAGE_UNREACHABLE),
        ],
    )
    def test_status_mapping(self, status, expected):
        assert VideoProber._classify_failure(status) is expected

    def test_cf_ray_detection_is_case_insensitive(self):
        headers = {"server": "cloudflare", "cf-ray": "abc-DUS"}

        assert VideoProber._served_by_storage_node(headers) is False


class TestStorageFaultAttribution:
    @pytest.mark.parametrize(
        "reason",
        [
            ProbeFailureReason.FILE_MISSING_ON_NODE,
            ProbeFailureReason.FILE_MISSING_IN_CATALOG,
            ProbeFailureReason.STORAGE_ERROR,
            ProbeFailureReason.STORAGE_UNREACHABLE,
            ProbeFailureReason.ORIGIN_UNREACHABLE,
            ProbeFailureReason.ORIGIN_TLS_ERROR,
            ProbeFailureReason.INVALID_METADATA,
        ],
    )
    def test_storage_faults(self, reason):
        assert reason.is_storage_fault is True

    @pytest.mark.parametrize(
        "reason",
        [
            ProbeFailureReason.LINK_REJECTED,
            ProbeFailureReason.IP_BLOCKED,
            ProbeFailureReason.RATE_LIMITED,
            ProbeFailureReason.VIDEO_TOO_SMALL,
            ProbeFailureReason.UNKNOWN,
        ],
    )
    def test_monitoring_side_failures_are_not_storage_faults(self, reason):
        """A rejected link or a blocked IP says nothing about the storage."""
        assert reason.is_storage_fault is False


class TestVideoExclusion:
    @pytest.mark.parametrize(
        "reason",
        [
            ProbeFailureReason.FILE_MISSING_ON_NODE,
            ProbeFailureReason.FILE_MISSING_IN_CATALOG,
            ProbeFailureReason.VIDEO_TOO_SMALL,
        ],
    )
    def test_dead_end_reasons_exclude_the_video(self, reason):
        """A missing or unmeasurable file can never produce a probe result."""
        assert reason.makes_video_unusable is True

    @pytest.mark.parametrize(
        "reason",
        [
            ProbeFailureReason.STORAGE_ERROR,
            ProbeFailureReason.STORAGE_UNREACHABLE,
            ProbeFailureReason.ORIGIN_UNREACHABLE,
            ProbeFailureReason.ORIGIN_TLS_ERROR,
            ProbeFailureReason.INVALID_METADATA,
            ProbeFailureReason.LINK_REJECTED,
            ProbeFailureReason.IP_BLOCKED,
            ProbeFailureReason.RATE_LIMITED,
            ProbeFailureReason.UNKNOWN,
        ],
    )
    def test_transient_reasons_keep_the_video(self, reason):
        """Anything that might succeed next run must stay in rotation."""
        assert reason.makes_video_unusable is False
