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
| id                  | Probe identifier                            |
| video_id            | Associated video                            |
| download_speed_mbps | Measured download speed (empty if failed)   |
| status              | Health status                               |
| failure_reason      | Why the probe produced no measurement       |
| created_at          | Probe timestamp                             |

---

## Probe Lifecycle

1. Select videos scheduled for probing.
2. Extract metadata with ffprobe, rejecting tiny videos.
3. Download a sample of the video.
4. Measure download speed.
5. Calculate storage baseline.
6. Determine probe status.
7. Save probe result.

**A probe costs two requests**, and that is a deliberate trade-off. Reading
metadata out of the already-downloaded sample would make it one, but the
sample is only the head of the file, so it works solely for containers whose
moov atom sits at the front. In practice one video in two or three has it at
the tail, which left the bitrate unknown and silently disabled the CRITICAL
check for them. Pointing ffprobe at the URL lets it seek with range requests
and read the tail, so metadata comes back for every video.

The cost is that each probe counts twice against the KVS anti-hotlink limiter,
which makes the IP whitelist below load-bearing rather than merely convenient.

---

## Failure Classification

A probe that produces no measurement is stored with `status = Failed` and a
`failure_reason`. The distinction that matters is **whose fault the failure
is** — only storage faults are held against the storage.

| Reason                | HTTP | Effect on the video     | Meaning                                                        |
| --------------------- | ---- | ----------------------- | -------------------------------------------------------------- |
| FileMissingOnNode     | 404  | excluded (`is_bad`)     | KVS redirected to a storage node, the file is not on its disk   |
| FileMissingInCatalog  | 404  | excluded (`is_bad`)     | KVS could not resolve the file at all, no redirect happened     |
| VideoTooSmall         | 200  | excluded (`is_bad`)     | Clip too small to measure a download speed against              |
| StorageError          | 5xx  | `errors_count` + 1      | Storage returned a server error                                 |
| StorageUnreachable    | —    | `errors_count` + 1      | Connection failed or timed out after retries                    |
| OriginUnreachable     | 52x  | `errors_count` + 1      | Cloudflare could not reach the origin; KVS never saw the request |
| OriginTlsError        | 525, 526 | `errors_count` + 1  | Cloudflare rejected the origin's SSL certificate                |
| InvalidMetadata       | 200  | `errors_count` + 1      | File was served but ffprobe could not read it                   |
| LinkRejected          | 403  | none                    | Link refused at the edge — usually the IP whitelist (see below) |
| IpBlocked             | 410  | none                    | Our IP is blocked by the KVS anti-hotlink rate limiter          |
| RateLimited           | 429  | none                    | We are probing too often from this IP                           |

The two flavours of 404 are told apart by the response headers: a node reply
carries no Cloudflare headers, because the redirect goes straight to the node.
This points the admin at a missing file on a specific node versus a broken
catalog entry.

Cloudflare's 52x codes are kept apart from ordinary 5xx for the same reason.
They are generated by the edge, not by KVS, and mean the request never reached
the origin at all — so they point at the origin server's networking or its TLS
certificate, not at anything the application did. `OriginTlsError` in
particular usually means an expired or mismatched certificate on the storage
node and will persist until someone renews it.

`is_bad` is a judgement about the **video, not the storage**: it marks a clip
that can never serve as a probe sample. Two things earn it, and both apply
after a single run, because neither can succeed later:

* the file is gone (either flavour of 404) — nothing left to measure;
* the clip is too small to time a download against.

Everything else keeps the video in rotation. A storage fault that might pass
next run — a 5xx, a timeout, an unreadable file — only increments
`errors_count` and never excludes the video.

Monitoring-side failures (`LinkRejected`, `IpBlocked`, `RateLimited`) are
logged and stored but counted nowhere: they say nothing about the storage, and
the video is fine.

Excluding a video does not lose the finding. The probe row keeps its
`failure_reason`, so missing files stay reportable after the video leaves the
rotation:

```sql
SELECT v.kvs_id, s.name, p.failure_reason, p.created_at
FROM probes p
JOIN videos v ON v.id = p.video_id
JOIN storages s ON s.id = v.storage_id
WHERE p.failure_reason IN ('FileMissingOnNode', 'FileMissingInCatalog')
ORDER BY p.created_at DESC;
```

### IP whitelist requirement

The server running this service **must have its IP in the KVS anti-hotlink
whitelist** (`ANTI_HOTLINK_WHITE_IPS`). Without it, KVS refuses the generated
links and every probe fails with `LinkRejected` (403) or `IpBlocked` (410) —
the response body is empty, so the cause is not obvious from the logs alone.

Whitelisting is handled by the **legacy-KVS team** — ask them when the service
is deployed to a new server or when its outbound IP changes. This is an
invisible dependency: nothing in the code enforces it, and a changed IP breaks
all probing silently.

The IP as KVS sees it can be checked with:

```bash
curl -sS https://pimpbunny.com/cdn-cgi/trace | grep '^ip='
```

It must match the `IP` value in `.env`, which is mixed into the link signature.

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

### Missing Bitrate

```text
video_missing_bitrate{storage_id, storage_name}
video_in_rotation{storage_id, storage_name}
```

How many videos still eligible for probing have no known bitrate, and how many
are eligible in total. Without a bitrate the CRITICAL rule cannot run and the
probe falls back to the storage baseline alone — so a storage where this climbs
is being monitored more weakly than the health counts suggest.

The usual cause is a container with its moov atom at the end: the probe only
downloads the head of the file, so ffprobe has nothing to read. Videos already
excluded from probing are not counted, and every storage reports a value even
when it is zero, so the gauge never goes stale after a storage recovers.

Useful as a ratio in Grafana:

```promql
video_missing_bitrate / video_in_rotation
```

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
