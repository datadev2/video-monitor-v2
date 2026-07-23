import pytest

from src.entities.video.model import Video
from src.entities.video.schemas import VideoCreate, VideoUpdate, VideoRead
from src.entities.video.services import VideoService


@pytest.mark.asyncio
class TestVideoService:
    async def test_create_video(self, async_session):
        service = VideoService(async_session)
        payload = VideoCreate(
            storage_id=1,
            kvs_id=999,
            server_group_id=10,
            video_format="_1080p",
            bitrate_mbps=5.0,
            duration_seconds=100.0,
            size_mb=200.0,
        )

        result = await service.create(payload)

        assert result.kvs_id == 999
        assert result.video_format == "_1080p"

        db_obj = await async_session.get(Video, result.id)
        assert db_obj is not None
        assert db_obj.kvs_id == 999

    async def test_get_video_by_kvs_id_found(self, async_session, video_mocks):
        service = VideoService(async_session)
        result = await service.get_video_from_kvs_id(video_mocks[0]["kvs_id"])

        assert result is not None
        assert result.kvs_id == video_mocks[0]["kvs_id"]

    async def test_get_video_by_kvs_id_not_found(self, async_session):
        service = VideoService(async_session)

        result = await service.get_video_from_kvs_id(999999)

        assert result is None

    async def test_get_videos_for_probe(self, async_session):
        service = VideoService(async_session)

        video1 = Video(
            storage_id=1,
            kvs_id=100500,
            server_group_id=10,
            video_format="1080p",
            is_bad=False,
        )
        video2 = Video(
            storage_id=1,
            kvs_id=200500,
            server_group_id=10,
            video_format="720p",
            is_bad=True,
        )
        video3 = Video(
            storage_id=1,
            kvs_id=300500,
            server_group_id=10,
            video_format="720p",
            is_bad=False,
        )

        async_session.add_all([video1, video2, video3])
        await async_session.commit()

        result = await service.get_videos_for_probe()

        kvs_ids = {v.kvs_id for v in result}

        assert 100500 in kvs_ids
        assert 300500 in kvs_ids
        assert 200500 not in kvs_ids

    async def test_update_video_metadata(self, async_session):
        service = VideoService(async_session)

        video = Video(
            storage_id=1,
            kvs_id=100,
            server_group_id=10,
            video_format="1080p",
        )

        async_session.add(video)
        await async_session.commit()
        await async_session.refresh(video)

        update = VideoUpdate(
            bitrate_mbps=9.9,
            size_mb=999.0,
        )

        result = await service.update_video_metadata(video.id, update)

        assert result.bitrate_mbps == 9.9
        assert result.size_mb == 999.0

        db_obj = await async_session.get(Video, video.id)
        assert db_obj.bitrate_mbps == 9.9

    async def test_mark_video_with_error_marks_bad_immediately(self, async_session):
        service = VideoService(async_session)

        video = Video(
            storage_id=1,
            kvs_id=200,
            server_group_id=10,
            video_format="1080p",
            errors_count=0,
            is_bad=False,
        )

        async_session.add(video)
        await async_session.commit()
        await async_session.refresh(video)

        video_read = await service.mark_video_with_error(
            VideoRead.model_validate(video)
        )

        assert video_read.errors_count == 1
        assert video_read.is_bad is True
        assert video_read.last_error_date is not None

    async def test_check_errors_and_mark_video_with_error_under_limit(
        self, async_session
    ):
        service = VideoService(async_session)

        video = Video(
            storage_id=1,
            kvs_id=201,
            server_group_id=10,
            video_format="1080p",
            errors_count=1,
            is_bad=False,
        )

        async_session.add(video)
        await async_session.commit()
        await async_session.refresh(video)

        video_read = await service.check_errors_and_mark_video_with_error(
            VideoRead.model_validate(video)
        )

        assert video_read.errors_count == 2
        assert video_read.is_bad is False
        assert video_read.last_error_date is not None

    async def test_check_errors_and_mark_video_with_error_becomes_bad(
        self, async_session
    ):
        service = VideoService(async_session)

        video = Video(
            storage_id=1,
            kvs_id=202,
            server_group_id=10,
            video_format="1080p",
            errors_count=2,
            is_bad=False,
        )

        async_session.add(video)
        await async_session.commit()
        await async_session.refresh(video)

        result = await service.check_errors_and_mark_video_with_error(
            VideoRead.model_validate(video)
        )

        assert result.errors_count == 3
        assert result.is_bad is True
