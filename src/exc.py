from src.entities.probe.enums import ProbeFailureReason


class ProbeError(Exception):
    """
    Base class for probe failures.

    Carries the classified failure reason alongside the HTTP status
    that produced it, so callers can decide whether the failure is a
    storage defect or a monitoring-side problem without re-parsing
    error strings.
    """

    default_reason: ProbeFailureReason = ProbeFailureReason.UNKNOWN

    def __init__(
        self,
        message: str,
        reason: ProbeFailureReason | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason if reason is not None else self.default_reason
        self.status_code = status_code


class VideoTooSmallError(ProbeError):
    """Exception raised when video too small for probe"""

    default_reason = ProbeFailureReason.VIDEO_TOO_SMALL


class VideoMetadataError(ProbeError):
    """Exception raised when video metadata is invalid"""

    default_reason = ProbeFailureReason.INVALID_METADATA


class RetryableProbeError(ProbeError):
    """Exception raised when nothing answered and the probe will be retried"""

    default_reason = ProbeFailureReason.STORAGE_UNREACHABLE


class VideoDownloadError(ProbeError):
    """Exception raised when video download fails"""

    default_reason = ProbeFailureReason.UNKNOWN
