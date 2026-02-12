"""Tests for episode processor — run with: pytest tests/"""

import json
import os
import tempfile

from core import (
    EpisodeProcessor,
    PodcastEpisode,
    FakeTranscriber,
    LocalStorage,
    Downloader,
    TranscriptionResult,
)


# A test downloader that writes a small dummy file instead of hitting the network
class StubDownloader(Downloader):
    def download(self, url: str, dest_path: str) -> None:
        with open(dest_path, "wb") as f:
            f.write(b"\x00" * 1024)  # 1KB dummy file


def make_episode(**overrides) -> PodcastEpisode:
    defaults = {
        "title": "Test Episode",
        "description": "A test",
        "guid": "test-guid-001",
        "pub_date": "2026-01-01",
        "mp3_url": "https://example.com/test.mp3",
    }
    defaults.update(overrides)
    return PodcastEpisode(**defaults)


class TestEpisodeProcessor:
    def test_process_writes_transcription_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            processor = EpisodeProcessor(
                transcriber=FakeTranscriber(),
                storage=LocalStorage(output_dir=tmpdir),
                downloader=StubDownloader(),
            )

            path = processor.process(make_episode())

            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert data["episode"]["title"] == "Test Episode"
            assert "FAKE TRANSCRIPTION" in data["transcription"]["full_text"]

    def test_process_uses_episode_guid_for_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            processor = EpisodeProcessor(
                transcriber=FakeTranscriber(),
                storage=LocalStorage(output_dir=tmpdir),
                downloader=StubDownloader(),
            )

            path1 = processor.process(make_episode(guid="aaa"))
            path2 = processor.process(make_episode(guid="bbb"))

            assert path1 != path2

    def test_process_same_guid_overwrites(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            processor = EpisodeProcessor(
                transcriber=FakeTranscriber(),
                storage=LocalStorage(output_dir=tmpdir),
                downloader=StubDownloader(),
            )

            path1 = processor.process(make_episode(guid="same"))
            path2 = processor.process(make_episode(guid="same"))

            assert path1 == path2


class TestFakeTranscriber:
    def test_returns_transcription_result(self):
        transcriber = FakeTranscriber()
        with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
            f.write(b"\x00" * 512)
            f.flush()
            result = transcriber.transcribe(f.name)

        assert isinstance(result, TranscriptionResult)
        assert result.language == "sv"
        assert len(result.segments) > 0
