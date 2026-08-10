from prometheus_client import Gauge

from src.infrastructure.redis_client import redis_cli

baseline_metric = Gauge(
    "video_baseline",
    "Baseline by storage and quality",
    [
        "storage_id",
        "storage_name",
    ],
)

download_speed_metric = Gauge(
    "video_download_speed",
    "Average download speed",
    ["storage_id", "storage_name"],
)

status_metric = Gauge(
    "video_health_status",
    "Probe health status count by storage. Every value here is a verdict "
    "on delivery: Healthy, Warning and Critical grade measured speed, and "
    "Failed is the floor of that same scale - the storage was unreachable "
    "or returned no bytes at all. Failures that say nothing about delivery "
    "- a deleted video, an unreadable container, a blocked monitoring IP - "
    "are reported by video_probe_failures instead.",
    [
        "storage_id",
        "storage_name",
        "status",
    ],
)

probe_failures_metric = Gauge(
    "video_probe_failures",
    "Failed probes by storage and reason, whoever's fault they are. "
    "Use affects_health to tell apart the ones counted as Failed in "
    "video_health_status from the ones excluded from it.",
    [
        "storage_id",
        "storage_name",
        "reason",
        "affects_health",
    ],
)


missing_bitrate_metric = Gauge(
    "video_missing_bitrate",
    "Videos in rotation with no known bitrate, by storage. "
    "These probes cannot run the CRITICAL check and are graded "
    "on the storage baseline alone.",
    ["storage_id", "storage_name"],
)

videos_in_rotation_metric = Gauge(
    "video_in_rotation",
    "Videos currently eligible for probing, by storage",
    ["storage_id", "storage_name"],
)


#: Gauges rebuilt wholesale on every scrape from the analytics snapshot.
_SNAPSHOT_METRICS = (
    baseline_metric,
    download_speed_metric,
    status_metric,
    missing_bitrate_metric,
    videos_in_rotation_metric,
    probe_failures_metric,
)


def update_metrics() -> None:
    """
    Republish every gauge from whatever analytics last left in Redis.

    A gauge keeps every label combination it has ever been given, while
    analytics only reports combinations that currently exist. Without a
    reset, a storage that recovered - or a failure reason that stopped
    occurring - would keep its last non-zero value for the life of the
    process, and the dashboard would never come back down. So the whole
    set is cleared and rebuilt from the snapshot.

    The reset means a scrape landing mid-rebuild sees the affected
    series briefly missing rather than stale. That is the better of the
    two failure modes: a gap is visible, a frozen number is not.
    """
    for metric in _SNAPSHOT_METRICS:
        metric.clear()

    for item in redis_cli.get_records("baselines"):
        baseline_metric.labels(
            storage_id=item["storage_id"],
            storage_name=item["storage_name"],
        ).set(item["baseline"])

    for item in redis_cli.get_records("avg_download_speeds"):
        download_speed_metric.labels(
            storage_id=item["storage_id"],
            storage_name=item["storage_name"],
        ).set(item["avg_download_speed"])

    for item in redis_cli.get_records("missing_bitrate"):
        labels = {
            "storage_id": str(item["storage_id"]),
            "storage_name": item["storage_name"],
        }
        missing_bitrate_metric.labels(**labels).set(item["videos_without_bitrate"])
        videos_in_rotation_metric.labels(**labels).set(item["videos_total"])

    for item in redis_cli.get_records("probe_failures"):
        probe_failures_metric.labels(
            storage_id=str(item["storage_id"]),
            storage_name=item["storage_name"],
            reason=item["reason"],
            affects_health=str(item["affects_health"]).lower(),
        ).set(item["count"])

    for storage in redis_cli.get_records("health_statuses"):
        for status_data in storage["statuses"]:
            status_metric.labels(
                storage_id=str(storage["storage_id"]),
                storage_name=storage["storage_name"],
                status=status_data["status"],
            ).set(status_data["count"])
