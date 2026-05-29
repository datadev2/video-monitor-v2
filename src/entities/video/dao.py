from src.dao import BaseDAO
from src.entities.video.model import Video


class VideoDAO(BaseDAO[Video]):
    model = Video
