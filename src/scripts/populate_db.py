import asyncio
import json

from loguru import logger

from src.db import get_session
from src.entities.storage.schemas import StorageCreate
from src.entities.storage.services import StorageService
from src.entities.video.schemas import VideoCreate
from src.entities.video.services import VideoService


class DBPopulator:
    async def populate_db(self) -> None:
        with open("videos.json", "r") as file:
            data = json.load(file)
            async with get_session() as session:
                video_service = VideoService(session)
                storage_service = StorageService(session)
                for url, storage_name in data.items():
                    storage = await storage_service.get_by_name(storage_name)
                    if storage is None:
                        storage = await storage_service.create(
                            StorageCreate(name=storage_name)
                        )
                    video = await video_service.get_video_from_video_link(url)
                    if not video:
                        video = await video_service.create(
                            VideoCreate(url=url, storage_id=storage.id)
                        )
                        logger.info(f"Created video {video}")


if __name__ == "__main__":
    db_populator = DBPopulator()
    asyncio.run(db_populator.populate_db())
