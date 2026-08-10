from enum import Enum


class ProbeStatus(Enum):
    HEALTHY = "Healthy"
    WARNING = "Warning"
    CRITICAL = "Critical"
    FAILED = "Failed"


class ProbeFailureReason(Enum):
    """
    Why a probe did not produce a speed measurement.

    The distinction that matters is whose fault the failure is:
    a storage defect is a finding the service exists to report,
    while a monitoring-side failure says nothing about the storage
    and must not be held against it.
    """

    # storage faults
    FILE_MISSING_ON_NODE = "FileMissingOnNode"
    FILE_MISSING_IN_CATALOG = "FileMissingInCatalog"
    STORAGE_ERROR = "StorageError"
    STORAGE_UNREACHABLE = "StorageUnreachable"
    ORIGIN_UNREACHABLE = "OriginUnreachable"
    ORIGIN_TLS_ERROR = "OriginTlsError"
    INVALID_METADATA = "InvalidMetadata"

    # monitoring-side failures
    LINK_REJECTED = "LinkRejected"
    IP_BLOCKED = "IpBlocked"
    RATE_LIMITED = "RateLimited"
    VIDEO_TOO_SMALL = "VideoTooSmall"

    UNKNOWN = "Unknown"

    @property
    def is_storage_fault(self) -> bool:
        """
        Whether the failure should be counted against the storage.

        Only storage faults increment the video error counter and can
        eventually mark a video as bad. Monitoring-side failures (a
        rejected link, a blocked IP) are our own problem and are logged
        without penalising the storage.
        """
        return self in _STORAGE_FAULTS

    @property
    def affects_storage_health(self) -> bool:
        """
        Whether the storage was down or served nothing at all.

        Failed sits next to Warning and Critical, so it has to mean the
        same kind of thing they do: a verdict on delivery. It is reserved
        for the storage being unreachable, or reachable and returning no
        bytes - the floor of the same scale that Warning and Critical
        measure in Mbps.

        This is narrower than `is_storage_fault`, and the gap is the
        point. Two kinds of failure are storage faults yet say nothing
        about delivery:

        - a missing file: the probe asked for something that no longer
          exists, so the storage was never given a chance to serve it;
        - unreadable metadata: the bytes arrived, ffprobe simply could
          not find a bitrate in the container.

        Both would let a content cleanup, or a moov atom at the tail of
        a file, read as a degraded storage. They stay visible through
        the per-reason failure breakdown instead.
        """
        return self in HEALTH_AFFECTING_REASONS

    @property
    def makes_video_unusable(self) -> bool:
        """
        Whether the video can never yield a measurement again.

        A missing file and a clip too short to time are both dead ends as
        probe samples, so the video is excluded after a single run rather
        than retried every hour. This takes precedence over the storage
        fault counter: the probe record keeps the reason, so excluding the
        video does not lose the finding.
        """
        return self in _UNUSABLE_VIDEO


_STORAGE_FAULTS = frozenset(
    {
        ProbeFailureReason.FILE_MISSING_ON_NODE,
        ProbeFailureReason.FILE_MISSING_IN_CATALOG,
        ProbeFailureReason.STORAGE_ERROR,
        ProbeFailureReason.STORAGE_UNREACHABLE,
        ProbeFailureReason.ORIGIN_UNREACHABLE,
        ProbeFailureReason.ORIGIN_TLS_ERROR,
        ProbeFailureReason.INVALID_METADATA,
    }
)

#: Reasons that count against a storage in the health status gauge:
#: the storage was unreachable, or reachable and served no bytes.
#:
#: Deliberately absent: a missing file (nothing was asked of the storage
#: that it could have served) and unreadable metadata (the bytes arrived
#: fine, we just could not parse them). Both stay visible in the
#: per-reason failure breakdown. See `affects_storage_health`.
HEALTH_AFFECTING_REASONS = frozenset(
    {
        ProbeFailureReason.STORAGE_ERROR,
        ProbeFailureReason.STORAGE_UNREACHABLE,
        ProbeFailureReason.ORIGIN_UNREACHABLE,
        ProbeFailureReason.ORIGIN_TLS_ERROR,
    }
)

_UNUSABLE_VIDEO = frozenset(
    {
        ProbeFailureReason.FILE_MISSING_ON_NODE,
        ProbeFailureReason.FILE_MISSING_IN_CATALOG,
        ProbeFailureReason.VIDEO_TOO_SMALL,
    }
)
