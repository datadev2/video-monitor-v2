from fastapi import APIRouter
from loguru import logger

from src.link_generator.link_generator import video_link_generator
from src.link_generator.schemas import VideoLinkData, VideoDownloadData

router = APIRouter(
    prefix="/link-generator",
    tags=["link-generator"],
)


@router.post("/link-generator")
async def generate_kvs_link(data: VideoLinkData):
    video_link_generator.generate_kvs_link(
        server_group_id=data.server_group_id,
        video_id=data.video_id,
        video_format=data.video_format,
    )

    return {"ok": True}


@router.post("/download-link-generator")
async def generate_kvs_dowbload_link(data: VideoDownloadData):
    res = video_link_generator.build_download_url(
        server_group_id=data.server_group_id,
        video_id=data.video_id,
        video_format=data.video_format,
        download_filename=data.download_filename,
    )
    logger.warning(f"RES: {res}")
    return {"ok": True}
