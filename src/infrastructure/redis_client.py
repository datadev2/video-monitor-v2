import json

from redis import Redis

from src.config import config


type JSONValue = (
    dict[str, JSONValue] | list[JSONValue] | str | int | float | bool | None
)


class RedisClient:
    def __init__(self):
        self.client = Redis.from_url(config.redis_dsn.unicode_string())

    def push(self, queue: str, value: JSONValue) -> None:
        self.client.set(queue, json.dumps(value))

    def get(self, queue: str) -> JSONValue:
        raw = self.client.get(queue)

        if raw is None:
            return None

        return json.loads(raw)


redis_cli = RedisClient()
