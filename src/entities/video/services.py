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

    async def get_video_from_video_link(self, url: str) -> VideoRead | None:
        result = await self.dao.find_one(url=url)
        if result:
            return VideoRead.model_validate(result)
        return None

    async def get_videos_for_probe(self) -> list[VideoRead]:
        result = await self.dao.find_all()
        return [VideoRead.model_validate(result) for result in result]

    async def update_video_metadata(
        self, video_id: int, video_data: VideoUpdate
    ) -> VideoRead:
        video = await self.dao.update(id=video_id, **video_data.model_dump())
        await self.session.commit()
        return VideoRead.model_validate(video)
