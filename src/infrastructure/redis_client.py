import json

from redis import Redis

from src.config import config


class RedisClient:
    def __init__(self):
        self.client = Redis.from_url(config.redis_dsn.unicode_string())

    def push(self, queue: str, value: dict | list) -> None:
        self.client.rpush(queue, json.dumps(value))


redis_cli = RedisClient()
