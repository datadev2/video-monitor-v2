# Video Storage Monitoring Service

## Overview

Video Storage Monitoring Service is a background monitoring system that periodically checks video availability and download performance across storage backends.

The service downloads video metadata, measures actual download speed, calculates storage performance baselines, and classifies each probe result according to predefined health thresholds.

The collected metrics can be visualized in Grafana and exported to Prometheus.

---

## Features

* Periodic video probing
* Download speed measurement
* Video metadata extraction
* Automatic baseline calculation per storage
* Health classification
* Historical probe storage
* Prometheus metrics export
* Grafana dashboard support

---

## Architecture

```text
                +----------------+
                | Celery Beat    |
                +-------+--------+
                        |
                        v
                +----------------+
                | Probe Worker   |
                +-------+--------+
                        |
                        v
                +----------------+
                | Video Prober   |
                +-------+--------+
                        |
                        v
                +----------------+
                | PostgreSQL     |
                | videos         |
                | probes         |
                | storages       |
                +-------+--------+
                        |
                        v
                +----------------+
                | Analytics      |
                +-------+--------+
                        |
                        v
                +----------------+
                | Redis Cache    |
                +-------+--------+
                        |
                        v
                +----------------+
                | Prometheus     |
                +-------+--------+
                        |
                        v
                +----------------+
                | Grafana        |
                +----------------+
```

---

## Data Model

### Storage

Represents a physical or logical video storage backend.

| Field | Description        |
| ----- | ------------------ |
| id    | Storage identifier |
| name  | Storage name       |

---

### Video

Represents a monitored video.

| Field            | Description          |
| ---------------- | -------------------- |
| id               | Internal identifier  |
| kvs_id           | KVS video identifier |
| storage_id       | Associated storage   |
| server_group_id  | KVS server group     |
| video_format     | Video format         |
| bitrate_mbps     | Video bitrate        |
| duration_seconds | Video duration       |
| size_mb          | File size            |

---

### Probe

Stores a single monitoring result.

| Field               | Description             |
| ------------------- | ----------------------- |
| id                  | Probe identifier        |
| video_id            | Associated video        |
| download_speed_mbps | Measured download speed |
| status              | Health status           |
| created_at          | Probe timestamp         |

---

## Probe Lifecycle

1. Select videos scheduled for probing.
2. Download a sample of the video.
3. Measure download speed.
4. Extract metadata if not available.
5. Calculate storage baseline.
6. Determine probe status.
7. Save probe result.

---

## Status Classification

### Critical

Download speed is insufficient for video playback.

```python
download_speed_mbps < bitrate_mbps * 2
```

### Warning

Download speed is significantly below storage baseline.

```python
download_speed_mbps <= baseline / 2
```

### Healthy

Video download speed is within acceptable limits.

```python
download_speed_mbps > baseline / 2
```

---

## Baseline Calculation

Baseline is calculated independently for each storage.

Only healthy probe results are included.

```sql
SELECT AVG(download_speed_mbps)
FROM probes
WHERE status = 'healthy'
GROUP BY storage_id;
```

---

## Prometheus Metrics

### Storage Baseline

```text
video_storage_baseline_mbps
```

Current baseline download speed for a storage.

---

### Storage Download Speed

```text
video_storage_download_speed_mbps
```

Average measured download speed.

---

### Storage Health

```text
video_storage_health
```

Storage health indicator.

| Value | Meaning  |
| ----- | -------- |
| 0     | Healthy  |
| 1     | Warning  |
| 2     | Critical |

---

## Scheduling

Video probing is executed periodically by Celery Beat.

Example:

```python
CELERY_BEAT_SCHEDULE = {
    "run-video-probes": {
        "task": "run_video_probes",
        "schedule": 300,
    }
}
```

---

## Analytics

Analytics are calculated separately from the probing process.

Responsibilities:

* baseline calculation
* storage statistics
* health aggregation
* Prometheus metric generation

---

## Future Improvements

* Adaptive baseline calculation
* Storage trend analysis
* Alerting integration
* Per-region statistics
* Storage degradation forecasting
* Automated storage failover recommendations
