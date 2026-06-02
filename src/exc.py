class VideoTooSmallError(Exception):
    """Exception raised when video too small for probe"""

    pass


class VideoMetadataError(Exception):
    """Exception raised when video metadata is invalid"""

    pass


class RetryableVideoMetadataError(Exception):
    """Exception raised when metadata request will be retried"""

    pass


class VideoDownloadError(Exception):
    """Exception raised when video download fails"""

    pass


class RetryableVideoDownloadError(Exception):
    """Exception raised when video download fails and needs retry"""

    pass
