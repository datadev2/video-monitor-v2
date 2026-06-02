from src.link_generator.link_generator import VideoLinkGenerator


class TestLinkGenerator:
    def test_get_content_directory(self):
        assert VideoLinkGenerator.get_content_directory(571151) == 571000
        assert VideoLinkGenerator.get_content_directory(999) == 0
        assert VideoLinkGenerator.get_content_directory(1000) == 1000
        assert VideoLinkGenerator.get_content_directory(1001) == 1000

    def test_generate_base_hash(self):
        service = VideoLinkGenerator()

        result = service._generate_base_hash(
            content_dir=571000,
            video_id=571151,
            video_format="_1080p.mp4",
        )

        assert len(result) == 32

    def test_generate_check_hash(self):
        service = VideoLinkGenerator()

        result = service._generate_check_hash(
            encoded_hash="abcdef123456",
            ip="1.2.3.4",
        )

        assert len(result) == 10

    def test_build_url(self):
        service = VideoLinkGenerator()

        url = service.build_url(
            server_group_id=42,
            content_dir=571000,
            video_id=571151,
            video_format="_1080p.mp4",
            base_hash="abc",
            check_hash="def",
        )

        assert (
            url
            == "https://pimpbunny.com/get_file/42/abcdef/571000/571151/571151_1080p.mp4/"
        )
