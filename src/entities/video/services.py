from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.config import config
from src.entities.video.dao import VideoDAO
from src.entities.video.model import Video
from src.entities.video.schemas import VideoRead, VideoCreate, VideoUpdate


class VideoService:
    """Service for managing monitored video records."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.dao = VideoDAO(self.session)

    async def create(self, video: VideoCreate) -> VideoRead:
        """
        Create a new video record.

        Args:
            video: Video data to persist.

        Returns:
            VideoRead: Created video record.
        """
        result = await self.dao.create(**video.model_dump())
        await self.session.commit()
        return VideoRead.model_validate(result)

    async def get_video_from_kvs_id(self, kvs_id: int) -> VideoRead | None:
        """
        Retrieve a video by its KVS identifier.

        Args:
            kvs_id: KVS video identifier.

        Returns:
            VideoRead | None: Video record if found, otherwise None.
        """
        result = await self.dao.find_one(kvs_id=kvs_id)
        if result:
            return VideoRead.model_validate(result)
        return None

    async def get_videos_for_probe(self) -> list[VideoRead]:
        """
        Retrieve videos eligible for probing.

        Picks a random sample of videos per storage (limited by
        config.probes_per_storage) instead of every video at once,
        so a single run doesn't hammer a storage with a full batch
        of requests.

        Returns:
            list[VideoRead]: Videos that are not marked as bad and
                can be processed by the probe worker.
        """
        row_number = (
            func.row_number()
            .over(partition_by=Video.storage_id, order_by=func.random())
            .label("row_number")
        )
        subq = select(Video, row_number).where(Video.is_bad.is_(False)).subquery()
        ranked_video = aliased(Video, subq)
        stmt = select(ranked_video).where(
            subq.c.row_number <= config.probes_per_storage
        )
        result = await self.session.execute(stmt)
        return [VideoRead.model_validate(r) for r in result.scalars().all()]

    async def update_video_metadata(
        self, video_id: int, video_data: VideoUpdate
    ) -> VideoRead:
        """
        Update video metadata collected during probing.

        Args:
            video_id: Video identifier.
            video_data: Metadata to update.

        Returns:
            VideoRead: Updated video record.
        """
        video = await self.dao.update(id=video_id, **video_data.model_dump())
        await self.session.commit()
        return VideoRead.model_validate(video)

    async def mark_video_with_error(self, video: VideoRead) -> VideoRead:
        """
        Register a probe failure for a video.

        Marks the video as bad.

        Args:
            video: Video record for which the probe failed.

        Returns:
            VideoRead: Updated video record.
        """
        is_bad = True

        last_error_date = datetime.now(timezone.utc)
        video_data = VideoUpdate(
            errors_count=1, is_bad=is_bad, last_error_date=last_error_date
        )
        updated_video = await self.dao.update(id=video.id, **video_data.model_dump())
        await self.session.commit()
        return VideoRead.model_validate(updated_video)

    async def check_errors_and_mark_video_with_error(
        self, video: VideoRead
    ) -> VideoRead:
        """
        Register a probe failure for a video.

        Increments the error counter and marks the video as bad
        after three consecutive errors.

        Args:
            video: Video record for which the probe failed.

        Returns:
            VideoRead: Updated video record.
        """
        errors_count = video.errors_count + 1
        if errors_count >= 3:
            is_bad = True
        else:
            is_bad = False
        last_error_date = datetime.now(timezone.utc)
        video_data = VideoUpdate(
            errors_count=errors_count, is_bad=is_bad, last_error_date=last_error_date
        )
        updated_video = await self.dao.update(id=video.id, **video_data.model_dump())
        await self.session.commit()
        return VideoRead.model_validate(updated_video)
