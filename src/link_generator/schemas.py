from pydantic import BaseModel


class VideoLinkData(BaseModel):
    server_group_id: int
    video_id: int
    video_format: str


class VideoDownloadData(BaseModel):
    server_group_id: int
    video_id: int
    video_format: str
    download_filename: str
