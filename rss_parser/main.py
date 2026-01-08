import hashlib
import json
import os

import feedparser
import requests
from google.cloud import storage

RSS_FEEDS = [
    "https://sr-restored.se/rss/5466"  # Dick Harrison svarar
]

# GCS configuration
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "sverige-radio-transcription")
STATE_BLOB_NAME = "_state/rss_state.json"


def load_state(bucket: storage.Bucket) -> dict:
    """Load previously seen episode GUIDs from GCS."""
    blob = bucket.blob(STATE_BLOB_NAME)
    try:
        if blob.exists():
            content = blob.download_as_text()
            return json.loads(content)
    except Exception as e:
        print(f"Warning: Could not load state from GCS: {e}")
    return {"seen_guids": []}


def save_state(bucket: storage.Bucket, state: dict) -> None:
    """Save seen episode GUIDs to GCS."""
    blob = bucket.blob(STATE_BLOB_NAME)
    blob.upload_from_string(
        json.dumps(state, indent=2), content_type="application/json"
    )


def get_mp3_url(entry) -> str | None:
    """Extract MP3 URL from RSS entry."""
    # Check enclosures first (standard podcast format)
    for enclosure in entry.get("enclosures", []):
        url = enclosure.get("url") or enclosure.get("href")
        if enclosure.get("type", "").startswith("audio/") or (
            url and url.endswith(".mp3")
        ):
            return url

    # Check links
    for link in entry.get("links", []):
        url = link.get("url") or link.get("href")
        if link.get("type", "").startswith("audio/") or (url and url.endswith(".mp3")):
            return url

    return None


def upload_to_gcs(
    bucket: storage.Bucket, mp3_url: str, episode_title: str, feed_title: str
) -> str | None:
    """Download MP3 and upload to GCS. Returns GCS path or None on failure."""
    try:
        # Create a safe filename
        safe_feed_title = "".join(
            c if c.isalnum() or c in " -_" else "_" for c in feed_title
        ).strip()
        safe_episode_title = "".join(
            c if c.isalnum() or c in " -_" else "_" for c in episode_title
        ).strip()

        # Create unique filename using URL hash
        url_hash = hashlib.md5(mp3_url.encode()).hexdigest()[:8]
        blob_name = f"{safe_feed_title}/{safe_episode_title}_{url_hash}.mp3"

        # Check if already uploaded
        blob = bucket.blob(blob_name)
        if blob.exists():
            print(f"  Already in GCS: {blob_name}")
            return blob_name

        # Download MP3
        print(f"  Downloading: {mp3_url}")
        response = requests.get(mp3_url, stream=True, timeout=300)
        response.raise_for_status()

        # Upload to GCS
        print(f"  Uploading to GCS: {blob_name}")
        blob.upload_from_string(response.content, content_type="audio/mpeg")

        return blob_name
    except Exception as e:
        print(f"  Error uploading {mp3_url}: {e}")
        return None


def fetch_and_process_feeds() -> None:
    """Fetch RSS feeds, find new episodes, and upload MP3s to GCS."""
    # Initialize GCS client
    storage_client = storage.Client()
    bucket = storage_client.bucket(GCS_BUCKET_NAME)

    state = load_state(bucket)
    seen_guids = set(state.get("seen_guids", []))
    new_guids = []

    for feed_url in RSS_FEEDS:
        print(f"\nProcessing feed: {feed_url}")

        try:
            feed = feedparser.parse(feed_url)
            feed_title = feed.get("title", "Unknown Feed")
            print(f"Feed title: {feed_title}")
            print(f"Found {len(feed.entries)} entries")

            for entry in feed.entries:
                guid = entry.get("id") or entry.get("link") or entry.get("title")

                if guid in seen_guids:
                    continue

                title = entry.get("title", "Unknown Episode")
                print(f"\nNew episode: {title}")

                mp3_url = get_mp3_url(entry)
                if mp3_url:
                    gcs_path = upload_to_gcs(bucket, mp3_url, title, feed_title)  # type: ignore
                    if gcs_path:
                        print(f"  Stored at: gs://{GCS_BUCKET_NAME}/{gcs_path}")
                else:
                    print(f"  No MP3 found for this entry")

                new_guids.append(guid)

        except Exception as e:
            print(f"Error processing feed {feed_url}: {e}")

    # Update state with new guids
    if new_guids:
        state["seen_guids"] = list(seen_guids | set(new_guids))
        save_state(bucket, state)
        print(f"\nProcessed {len(new_guids)} new episodes")
    else:
        print("\nNo new episodes found")


def main():
    print("RSS Parser - Fetching feeds and uploading to GCS")
    fetch_and_process_feeds()


if __name__ == "__main__":
    main()
