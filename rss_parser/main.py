import hashlib
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional

import feedparser
import requests
from google.cloud import storage

RSS_FEEDS = [
    "https://sr-restored.se/rss/5466"  # Dick Harrison svarar
]


@dataclass
class PodcastEpisode:
    """Represents a single podcast episode extracted from RSS."""

    title: str
    description: str
    guid: str
    pub_date: str
    mp3_url: str


@dataclass
class Feed:
    title: str
    podcast_episodes: list[PodcastEpisode]


def parse_rss_feed(feed_url: str) -> Feed:
    """
    Parse an RSS feed and extract all episodes with their MP3 URLs.

    Args:
        feed_url: URL of the RSS feed to parse

    Returns:
        List of PodcastEpisode objects
    """
    feed = feedparser.parse(feed_url)
    episodes = []

    feed_title = feed.feed.get("title", "")  # type: ignore
    for entry in feed.entries:
        episode = PodcastEpisode(
            title=entry.get("title", ""),  # type: ignore
            description=entry.get("description", ""),  # type: ignore
            guid=entry.get("guid", ""),  # type: ignore
            pub_date=entry.get("published", ""),  # type: ignore
            mp3_url=entry.get("enclosures", [{}])[0].get("url", ""),  # type: ignore
        )
        episodes.append(episode)

    return Feed(title=feed_title, podcast_episodes=episodes)


def fetch_and_process_feeds():
    """Fetch all RSS feeds and process their episodes."""

    feeds: list[Feed] = []

    for feed_url in RSS_FEEDS:
        print(f"Fetching feed: {feed_url}")
        feed = parse_rss_feed(feed_url)

        feeds.extend([feed])

    return feeds


def upload_to_gcs(feeds: list[Feed], bucket_name: str, blob_name: str):
    """
    Upload feeds as JSON to Google Cloud Storage.

    Args:
        feeds: List of Feed objects to upload
        bucket_name: Name of the GCS bucket
        blob_name: Name of the blob (e.g., 'feeds.json')
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    # Convert feeds to JSON
    feeds_data = [asdict(feed) for feed in feeds]
    json_data = json.dumps(feeds_data, indent=2, ensure_ascii=False)

    # Upload the JSON blob
    blob.upload_from_string(json_data, content_type="application/json")
    print(f"Uploaded {blob_name} to bucket {bucket_name}")


def list_files_in_folder(bucket_name: str, folder_prefix: str) -> list[str]:
    """
    List all files in a GCS folder.

    Args:
        bucket_name: Name of the GCS bucket
        folder_prefix: Folder path (e.g., 'my-folder/' or 'parent/child/')

    Returns:
        List of blob names
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    # List all blobs with the given prefix
    blobs = bucket.list_blobs(prefix=folder_prefix)

    return [blob.name for blob in blobs]


# Example usage:


def main():
    print("RSS Parser - Fetching feeds and extracting episodes")
    feeds = fetch_and_process_feeds()

    # Upload to Google Cloud Storage
    upload_to_gcs(
        feeds=feeds, bucket_name="sverige-radio-transcription", blob_name="feeds.json"
    )
    print("Done uploading feeds.json!")

    files = list_files_in_folder("sverige-radio-transcription", "")

    print("Files in bucket:")


if __name__ == "__main__":
    main()
