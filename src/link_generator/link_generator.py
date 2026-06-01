import hashlib

from loguru import logger

from src.config import config


class VideoLinkGenerator:
    def __init__(self):
        self.base_url = "https://pimpbunny.com"
        self.cv = config.kvs_cv
        self.ahv = config.kvs_ahv
        self.ip = config.ip

    def generate_kvs_link(
        self,
        server_group_id: int,
        video_id: int,
        video_format: str,
    ):
        content_dir = self.get_content_directory(video_id)
        base_hash = self._generate_base_hash(content_dir, video_id, video_format)

        encoded_hash = self._encode_hash(hash_value=base_hash, ahv=self.ahv)
        check_hash = self._generate_check_hash(encoded_hash=encoded_hash, ip=self.ip)

        res = self.build_url(
            server_group_id=server_group_id,
            content_dir=content_dir,
            video_id=video_id,
            video_format=video_format,
            base_hash=base_hash,
            check_hash=check_hash,
        )
        logger.info(f"generated url: {res}")
        return res

    def build_url(
        self,
        server_group_id: int,
        content_dir: int,
        video_id: int,
        video_format: str,
        base_hash: str,
        check_hash: str,
    ) -> str:
        return (
            f"{self.base_url}/get_file/"
            f"{server_group_id}/"
            f"{base_hash}{check_hash}/"
            f"{content_dir}/"
            f"{video_id}/"
            f"{video_id}{video_format}/"
        )

    def _generate_check_hash(
        self,
        encoded_hash: str,
        ip: str,
    ) -> str:
        raw = f"{encoded_hash}{self.cv}{ip}"

        return hashlib.md5(raw.encode()).hexdigest()[:10]

    def _encode_hash(self, hash_value: str, ahv: str) -> str:
        hash_list = list(hash_value)

        for i in range(len(hash_list)):
            new_pos = i

            for j in range(i, len(ahv)):
                new_pos += int(ahv[j])

            while new_pos >= len(hash_list):
                new_pos -= len(hash_list)

            hash_list[i], hash_list[new_pos] = (
                hash_list[new_pos],
                hash_list[i],
            )

        return "".join(hash_list)

    def _generate_base_hash(
        self,
        content_dir: int,
        video_id: int,
        video_format: str,
    ) -> str:
        raw = f"{self.cv}{content_dir}/{video_id}/{video_id}{video_format}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def get_content_directory(video_id: int) -> int:
        return (video_id // 1000) * 1000


video_link_generator = VideoLinkGenerator()
