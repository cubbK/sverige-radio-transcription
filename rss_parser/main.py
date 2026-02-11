import hashlib
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional

import feedparser
import flask
import functions_framework
import requests
from google.cloud import storage, tasks_v2

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


def fetch_existing_feeds() -> list[dict]:
    """Fetch existing feeds from GCS bucket."""
    client = storage.Client()
    bucket = client.bucket("sverige-radio-transcription")
    blob = bucket.blob("feeds.json")
    if not blob.exists():
        print("No existing feeds found in GCS.")
        return []
    data = blob.download_as_text()
    feeds_json = json.loads(data)
    return feeds_json


def get_existing_episode_guids(existing_feeds: list[dict]) -> set[str]:
    """Extract all episode GUIDs from existing feeds."""
    guids = set()
    for feed in existing_feeds:
        if "podcast_episodes" in feed:
            for episode in feed["podcast_episodes"]:
                guids.add(episode["guid"])
    return guids


def identify_new_episodes(
    feeds: list[Feed], existing_feeds: list[dict]
) -> list[PodcastEpisode]:
    """Identify episodes that are new (not in existing feeds)."""
    existing_guids = get_existing_episode_guids(existing_feeds)
    new_episodes = []

    for feed in feeds:
        for episode in feed.podcast_episodes:
            if episode.guid not in existing_guids:
                new_episodes.append(episode)

    return new_episodes


def dispatch_to_cloud_tasks(
    project: str,
    queue: str,
    location: str,
    episode: PodcastEpisode,
):
    """
    Dispatch a Cloud Task for a new podcast episode.

    Args:
        project: Google Cloud project ID
        queue: Cloud Tasks queue name
        location: Queue location (e.g., 'europe-west1')
        episode: PodcastEpisode object to process
    """
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project, location, queue)

    # Convert episode to dict for JSON serialization
    episode_data = asdict(episode)

    url = os.environ["EPISODE_PROCESSOR_URL"]

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(episode_data).encode(),
            "oidc_token": {
                "service_account_email": os.environ.get(
                    "GOOGLE_CLOUD_SERVICE_ACCOUNT", ""
                ),
            },
        }
    }

    response = client.create_task(request={"parent": parent, "task": task})
    print(f"Dispatched task for episode: {episode.title}")
    print(f"Task name: {response.name}")


def main():
    print("RSS Parser - Fetching feeds and extracting episodes")
    feeds = fetch_and_process_feeds()

    existing_feeds: list[dict] = fetch_existing_feeds()

    # Identify new episodes
    new_episodes = identify_new_episodes(feeds, existing_feeds)
    print(f"Found {len(new_episodes)} new episodes")

    # Dispatch Cloud Task for each new episode
    if new_episodes:
        project = os.getenv("GCP_PROJECT_ID", "sverige-radio-transcription")
        queue = os.getenv("CLOUD_TASKS_QUEUE", "podcast-processing")
        location = os.getenv("CLOUD_TASKS_LOCATION", "europe-west1")

        for episode in new_episodes:
            try:
                dispatch_to_cloud_tasks(project, queue, location, episode)
            except Exception as e:
                print(f"Error dispatching task for {episode.title}: {e}")

    # Upload to Google Cloud Storage
    upload_to_gcs(
        feeds=feeds, bucket_name="sverige-radio-transcription", blob_name="feeds.json"
    )


@functions_framework.http
def rss_parser_entry(request: flask.Request) -> flask.Response:
    """Cloud Function entry point for the RSS parser."""
    main()
    return flask.Response("OK", status=200)


@functions_framework.http
def process_episode(request: flask.Request) -> flask.Response:
    """Cloud Function entry point for processing a single episode."""
    episode_data = request.get_json(silent=True)
    if not episode_data:
        return flask.Response("No episode data provided", status=400)

    episode = PodcastEpisode(**episode_data)
    print(f"Processing episode: {episode.title}")
    print(f"MP3 URL: {episode.mp3_url}")

    # TODO: Add your episode processing logic here
    # e.g., download MP3, transcribe, store results

    return flask.Response(f"Processed: {episode.title}", status=200)


if __name__ == "__main__":
    main()
