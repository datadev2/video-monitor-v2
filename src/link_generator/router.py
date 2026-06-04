from fastapi import APIRouter, Depends

from src.auth import basic_auth
from src.link_generator.link_generator import video_link_generator
from src.link_generator.schemas import VideoLinkData

router = APIRouter(
    prefix="/link-generator",
    tags=["link-generator"],
    dependencies=[Depends(basic_auth)],
)


@router.post("/link-generator")
async def generate_kvs_link(data: VideoLinkData):
    video_link_generator.generate_kvs_link(
        server_group_id=data.server_group_id,
        video_id=data.video_id,
        video_format=data.video_format,
    )

    return {"ok": True}
