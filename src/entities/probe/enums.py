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

_UNUSABLE_VIDEO = frozenset(
    {
        ProbeFailureReason.FILE_MISSING_ON_NODE,
        ProbeFailureReason.FILE_MISSING_IN_CATALOG,
        ProbeFailureReason.VIDEO_TOO_SMALL,
    }
)
