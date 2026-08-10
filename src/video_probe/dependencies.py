from loguru import logger

from starlette.exceptions import HTTPException

from src.exc import VideoDownloadError, VideoMetadataError, VideoTooSmallError
from src.video_probe.schemas import VideoLink, VideoProbe
from src.video_probe.video_prober import video_prober


async def probe_video(video: VideoLink) -> VideoProbe:
    """
    Probe a video URL on behalf of a request, mapping failures to HTTP.

    Args:
        video: Requested video link.

    Returns:
        VideoProbe: Collected metadata and download statistics.

    Raises:
        HTTPException: For any probe failure, with a status that
            reflects whose problem it is.
    """
    try:
        return await video_prober.probe(video.url)
    except VideoTooSmallError as e:
        logger.debug(e)
        raise HTTPException(status_code=400, detail="Video Too Small")
    except VideoDownloadError as e:
        logger.debug(e)
        raise HTTPException(status_code=404, detail="Video Download Failed")
    except VideoMetadataError as e:
        logger.warning(e)
        raise HTTPException(status_code=500, detail="Video Probe Failed")
