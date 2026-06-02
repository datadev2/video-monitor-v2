from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.video.dao import VideoDAO
from src.entities.video.schemas import VideoRead, VideoCreate, VideoUpdate


class VideoService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.dao = VideoDAO(self.session)

    async def create(self, video: VideoCreate) -> VideoRead:
        result = await self.dao.create(**video.model_dump())
        await self.session.commit()
        return VideoRead.model_validate(result)

    async def get_video_from_kvs_id(self, kvs_id: int) -> VideoRead | None:
        result = await self.dao.find_one(kvs_id=kvs_id)
        if result:
            return VideoRead.model_validate(result)
        return None

    async def get_videos_for_probe(self) -> list[VideoRead]:
        result = await self.dao.find_all(is_bad=False)
        return [VideoRead.model_validate(r) for r in result]

    async def update_video_metadata(
        self, video_id: int, video_data: VideoUpdate
    ) -> VideoRead:
        video = await self.dao.update(id=video_id, **video_data.model_dump())
        await self.session.commit()
        return VideoRead.model_validate(video)

    async def mark_video_with_error(self, video: VideoRead) -> VideoRead:
        errors_count = video.errors_count + 1
        if errors_count >= 3:
            is_bad = True
        else:
            is_bad = False
        last_error_date = datetime.now(timezone.utc)
        video_data = VideoUpdate(
            errors_count=errors_count, is_bad=is_bad, last_error_date=last_error_date
        )
        video = await self.dao.update(id=video.id, **video_data.model_dump())
        await self.session.commit()
        return VideoRead.model_validate(video)
