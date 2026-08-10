import pytest
from prometheus_client import generate_latest

import src.infrastructure.prometheus as prometheus


@pytest.fixture
def fake_redis(monkeypatch):
    """Drive update_metrics from an in-memory analytics snapshot."""
    snapshot: dict[str, list] = {}
    monkeypatch.setattr(
        prometheus.redis_cli,
        "get_records",
        lambda key: snapshot.get(key, []),
    )
    return snapshot


def _series(needle: str) -> dict[str, float]:
    return {
        line.split(" ")[0]: float(line.split(" ")[1])
        for line in generate_latest().decode().splitlines()
        if line.startswith(needle) and "{" in line
    }


class TestGaugesFollowRecovery:
    """
    Gauges are rebuilt from a snapshot, so they must also shrink.

    A gauge remembers every label combination it was ever given. If a
    storage recovers, analytics simply stops reporting the failing
    combination - nothing tells the gauge to drop it, so without a
    reset it would serve the last bad number indefinitely.
    """

    def test_resolved_failures_disappear(self, fake_redis):
        fake_redis["probe_failures"] = [
            {
                "storage_id": 1,
                "storage_name": "s1",
                "reason": "StorageError",
                "count": 7,
                "affects_health": True,
            }
        ]
        prometheus.update_metrics()
        assert _series("video_probe_failures")

        fake_redis["probe_failures"] = []
        prometheus.update_metrics()

        assert _series("video_probe_failures") == {}

    def test_failed_status_drops_when_it_stops_being_reported(self, fake_redis):
        fake_redis["health_statuses"] = [
            {
                "storage_id": 1,
                "storage_name": "s1",
                "statuses": [
                    {"status": "Failed", "count": 7},
                    {"status": "Healthy", "count": 3},
                ],
            }
        ]
        prometheus.update_metrics()

        fake_redis["health_statuses"] = [
            {
                "storage_id": 1,
                "storage_name": "s1",
                "statuses": [{"status": "Healthy", "count": 10}],
            }
        ]
        prometheus.update_metrics()

        series = _series("video_health_status")

        assert not any("Failed" in name for name in series)
        assert any("Healthy" in name and value == 10 for name, value in series.items())

    def test_a_storage_that_stops_reporting_is_dropped(self, fake_redis):
        fake_redis["baselines"] = [
            {"storage_id": 9, "storage_name": "retired", "baseline": 55.0}
        ]
        prometheus.update_metrics()
        assert _series("video_baseline")

        fake_redis["baselines"] = []
        prometheus.update_metrics()

        assert _series("video_baseline") == {}
