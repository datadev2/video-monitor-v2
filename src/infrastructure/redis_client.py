import json
from typing import Any

from redis import Redis

from src.config import config


type JSONValue = (
    dict[str, JSONValue] | list[JSONValue] | str | int | float | bool | None
)


class RedisClient:
    def __init__(self) -> None:
        self.client = Redis.from_url(config.redis_dsn.unicode_string())

    def push(self, queue: str, value: JSONValue) -> None:
        self.client.set(queue, json.dumps(value))

    def get(self, queue: str) -> JSONValue:
        raw = self.client.get(queue)

        if raw is None:
            return None

        return json.loads(raw)

    def get_records(self, queue: str) -> list[dict[str, Any]]:
        """
        Read a list of JSON objects, treating anything else as empty.

        Every analytics key holds a list of flat records. A key that was
        never written yet - a fresh Redis, or a deploy before the first
        analytics run - must read as "nothing to publish" rather than
        blow up the metrics endpoint.

        Args:
            queue: Redis key to read.

        Returns:
            list[dict[str, Any]]: Stored records, empty if unavailable.
        """
        value = self.get(queue)

        if not isinstance(value, list):
            return []

        return [item for item in value if isinstance(item, dict)]


redis_cli = RedisClient()
