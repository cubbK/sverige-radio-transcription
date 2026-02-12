"""Interfaces and implementations for episode processing components.

This module separates concerns so each piece can be tested and swapped independently.
"""

import hashlib
import json
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests


@dataclass
class PodcastEpisode:
    title: str
    description: str
    guid: str
    pub_date: str
    mp3_url: str


@dataclass
class TranscriptionResult:
    language: str
    language_probability: float
    duration: float
    full_text: str
    segments: list[dict]


# ====================================================================
# Transcriber
# ====================================================================


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str) -> TranscriptionResult: ...


class WhisperTranscriber(Transcriber):
    """Production transcriber using faster-whisper on GPU."""

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
    ):
        from faster_whisper import WhisperModel

        print(f"Loading Whisper model: {model_size} on {device} ({compute_type})")
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        print("Model loaded successfully")

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        segments, info = self._model.transcribe(
            audio_path, language="sv", beam_size=5, vad_filter=True
        )
        segments_list = []
        full_text_parts = []
        for seg in segments:
            segments_list.append(
                {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
            )
            full_text_parts.append(seg.text.strip())

        return TranscriptionResult(
            language=info.language,
            language_probability=info.language_probability,
            duration=info.duration,
            full_text=" ".join(full_text_parts),
            segments=segments_list,
        )


class FakeTranscriber(Transcriber):
    """Instant fake transcriber for local development and tests."""

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        file_size = os.path.getsize(audio_path)
        return TranscriptionResult(
            language="sv",
            language_probability=0.99,
            duration=120.0,
            full_text=f"[FAKE TRANSCRIPTION] file={audio_path} size={file_size}",
            segments=[{"start": 0.0, "end": 120.0, "text": "[fake]"}],
        )


# ====================================================================
# Storage
# ====================================================================


class Storage(ABC):
    @abstractmethod
    def upload_transcription(
        self, episode: PodcastEpisode, result: TranscriptionResult
    ) -> str: ...


class GCSStorage(Storage):
    """Upload transcriptions to Google Cloud Storage."""

    def __init__(self, bucket_name: str):
        from google.cloud import storage

        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    def upload_transcription(
        self, episode: PodcastEpisode, result: TranscriptionResult
    ) -> str:
        safe_name = episode.guid
        blob_path = f"transcriptions/{safe_name}.json"

        data = {
            "episode": {
                "title": episode.title,
                "guid": episode.guid,
                "pub_date": episode.pub_date,
                "mp3_url": episode.mp3_url,
            },
            "transcription": {
                "language": result.language,
                "language_probability": result.language_probability,
                "duration": result.duration,
                "full_text": result.full_text,
                "segments": result.segments,
            },
        }

        blob = self._bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json",
        )
        print(f"Uploaded transcription to gs://{self._bucket.name}/{blob_path}")
        return blob_path


class LocalStorage(Storage):
    """Write transcriptions to a local directory — for dev/testing."""

    def __init__(self, output_dir: str = "output"):
        self._output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def upload_transcription(
        self, episode: PodcastEpisode, result: TranscriptionResult
    ) -> str:
        safe_name = hashlib.md5(episode.guid.encode()).hexdigest()
        path = os.path.join(self._output_dir, f"{safe_name}.json")

        data = {
            "episode": {
                "title": episode.title,
                "guid": episode.guid,
                "pub_date": episode.pub_date,
                "mp3_url": episode.mp3_url,
            },
            "transcription": {
                "language": result.language,
                "language_probability": result.language_probability,
                "duration": result.duration,
                "full_text": result.full_text,
                "segments": result.segments,
            },
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Wrote transcription to {path}")
        return path


# ====================================================================
# Downloader
# ====================================================================


class Downloader(ABC):
    @abstractmethod
    def download(self, url: str, dest_path: str) -> None: ...


class HTTPDownloader(Downloader):
    def download(self, url: str, dest_path: str) -> None:
        resp = requests.get(url, stream=True, timeout=300)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)


# ====================================================================
# Episode Processor — wires it all together
# ====================================================================


class EpisodeProcessor:
    """Coordinates download → transcribe → store."""

    def __init__(
        self,
        transcriber: Transcriber,
        storage: Storage,
        downloader: Downloader,
    ):
        self.transcriber = transcriber
        self.storage = storage
        self.downloader = downloader

    def process(self, episode: PodcastEpisode) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            mp3_path = os.path.join(tmpdir, "episode.mp3")

            print(f"Downloading: {episode.mp3_url}")
            self.downloader.download(episode.mp3_url, mp3_path)
            size_mb = os.path.getsize(mp3_path) / (1024 * 1024)
            print(f"Downloaded ({size_mb:.1f} MB)")

            print("Transcribing…")
            result = self.transcriber.transcribe(mp3_path)
            print(f"Done: {result.duration:.1f}s of audio")

        path = self.storage.upload_transcription(episode, result)
        return path
