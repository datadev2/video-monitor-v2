import json
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.config import config
from src.db import Base
from src.entities.probe.enums import ProbeStatus

from src.entities.probe.model import Probe
from src.entities.video.model import Video
from src.entities.storage.model import Storage
from src.main import app


@pytest.fixture(scope="function")
async def async_client():
    transport = ASGITransport(app=app)
    auth = (config.auth_user, config.auth_pass)
    async with AsyncClient(
        transport=transport, base_url="http://test", auth=auth
    ) as client:
        yield client


@pytest.fixture(scope="function")
async def engine():
    engine = create_async_engine(config.db_connection_string)
    yield engine
    await engine.dispose()


@pytest.fixture
async def async_session(engine):
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        yield session


def get_mock(entity: str) -> list:
    fpath = Path(f"tests/integrational_tests/mocks/{entity}.json")
    return json.loads(fpath.read_text(encoding="utf-8"))


@pytest.fixture
def storage_mocks():
    return get_mock("storages")


@pytest.fixture
def video_mocks():
    return get_mock("videos")


@pytest.fixture
def probe_mocks():
    return get_mock("probes")


def parse_datetime_fields(data: list[dict], *fields: str) -> None:
    for item in data:
        for field in fields:
            value = item.get(field)

            if value is not None:
                item[field] = datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture(scope="function", autouse=True)
async def prepare_database(engine):
    assert config.is_test_mode

    probe_status_enum = PgEnum(
        ProbeStatus,
        name="probe_status",
        values_callable=lambda obj: [e.value for e in obj],
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

        await conn.execute(sa.text("DROP TYPE IF EXISTS probe_status CASCADE"))

        await conn.run_sync(
            lambda sync_conn: probe_status_enum.create(
                sync_conn,
                checkfirst=True,
            )
        )

        await conn.run_sync(Base.metadata.create_all)

    storage_mock = get_mock(Storage.__tablename__)
    video_mock = get_mock(Video.__tablename__)
    probe_mock = get_mock(Probe.__tablename__)

    parse_datetime_fields(video_mock, "last_error_date")
    parse_datetime_fields(probe_mock, "created_at")

    # 🔥 ВАЖНО: используем engine connection pattern
    async with engine.begin() as conn:
        await conn.execute(sa.insert(Storage).values(storage_mock))
        await conn.execute(sa.insert(Video).values(video_mock))
        await conn.execute(sa.insert(Probe).values(probe_mock))
