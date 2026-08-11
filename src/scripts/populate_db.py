import asyncio
import json
from pathlib import Path

from loguru import logger

import src.entities.registry  # noqa: F401  (registers every mapped class)
from src.db import get_session
from src.entities.storage.schemas import StorageCreate
from src.entities.storage.services import StorageService
from src.entities.video.schemas import VideoCreate
from src.entities.video.services import VideoService

VIDEOS_FILE = Path("videos.json")


async def populate_db(source: Path = VIDEOS_FILE) -> None:
    """
    Seed storages and videos from a JSON dump, skipping what already exists.

    Args:
        source: JSON file holding the video records.
    """
    data = json.loads(source.read_text(encoding="utf-8"))

    async with get_session() as session:
        video_service = VideoService(session)
        storage_service = StorageService(session)

        for record in data:
            storage = await storage_service.get_by_name(record["storage"])
            if storage is None:
                storage = await storage_service.create(
                    StorageCreate(name=record["storage"])
                )

            video = await video_service.get_video_from_kvs_id(record["kvs_video_id"])
            if video is None:
                video = await video_service.create(
                    VideoCreate(
                        storage_id=storage.id,
                        kvs_id=record["kvs_video_id"],
                        server_group_id=record["server_group_id"],
                        video_format=record["video_format"],
                    )
                )
                logger.info(f"Created video {video}")


if __name__ == "__main__":
    asyncio.run(populate_db())
