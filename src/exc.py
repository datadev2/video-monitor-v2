class VideoTooSmallError(Exception):
    """Exception raised when video too small for probe"""

    pass


class VideoMetadataError(Exception):
    """Exception raised when video metadata is invalid"""

    pass


class VideoDownloadError(Exception):
    """Exception raised when video download fails"""

    pass
