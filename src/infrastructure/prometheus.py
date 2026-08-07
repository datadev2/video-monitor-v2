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
    "Video health status count by storage",
    [
        "storage_id",
        "storage_name",
        "status",
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


class MetricsService:
    def update_metrics(self):
        baselines = redis_cli.get("baselines") or []
        for item in baselines:
            baseline_metric.labels(
                storage_id=item["storage_id"],
                storage_name=item["storage_name"],
            ).set(item["baseline"])

        avg_download_speeds = redis_cli.get("avg_download_speeds") or []
        for item in avg_download_speeds:
            download_speed_metric.labels(
                storage_id=item["storage_id"],
                storage_name=item["storage_name"],
            ).set(item["avg_download_speed"])

        missing_bitrate = redis_cli.get("missing_bitrate") or []
        for item in missing_bitrate:
            labels = {
                "storage_id": str(item["storage_id"]),
                "storage_name": item["storage_name"],
            }
            missing_bitrate_metric.labels(**labels).set(item["videos_without_bitrate"])
            videos_in_rotation_metric.labels(**labels).set(item["videos_total"])

        health_statuses = redis_cli.get("health_statuses") or []
        for storage in health_statuses:
            for status_data in storage["statuses"]:
                status_metric.labels(
                    storage_id=str(storage["storage_id"]),
                    storage_name=storage["storage_name"],
                    status=status_data["status"],
                ).set(status_data["count"])


metrics_service = MetricsService()
