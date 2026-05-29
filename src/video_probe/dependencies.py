from fastapi import Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from starlette.exceptions import HTTPException

from src.db import get_async_session
from src.exc import VideoDownloadError, VideoMetadataError, VideoTooSmallError
from src.video_probe.schemas import VideoLink, VideoProbe
from src.video_probe.video_prober import video_prober


class ProbeDependencies:
    async def probe_video(
        self,
        video: VideoLink,
        session: AsyncSession = Depends(get_async_session),
    ) -> VideoProbe:
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


probe_dependencies = ProbeDependencies()
