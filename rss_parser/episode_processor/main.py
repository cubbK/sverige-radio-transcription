"""Flask HTTP server — thin wrapper around EpisodeProcessor."""

import os

from flask import Flask, request, Response

from core import (
    EpisodeProcessor,
    PodcastEpisode,
    WhisperTranscriber,
    FakeTranscriber,
    GCSStorage,
    LocalStorage,
    HTTPDownloader,
    log,
)

app = Flask(__name__)

# ----------------------------------------------------------------
# Build the processor based on environment
# ----------------------------------------------------------------
USE_FAKE = os.getenv("FAKE_MODE", "").lower() in ("1", "true", "yes")

if USE_FAKE:
    log("*** FAKE MODE — no GPU, no GCS, instant results ***")
    transcriber = FakeTranscriber()
    storage = LocalStorage(output_dir=os.getenv("OUTPUT_DIR", "output"))
else:
    transcriber = WhisperTranscriber(
        model_size=os.getenv("WHISPER_MODEL_SIZE", "large-v3"),
        device=os.getenv("WHISPER_DEVICE", "cuda"),
        compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "float16"),
    )
    storage = GCSStorage(
        bucket_name=os.getenv("GCS_BUCKET", "sverige-radio-transcription")
    )

processor = EpisodeProcessor(
    transcriber=transcriber,
    storage=storage,
    downloader=HTTPDownloader(),
)


@app.route("/", methods=["POST"])
def process_episode():
    episode_data = request.get_json(silent=True)
    if not episode_data:
        return Response("No episode data provided", status=400)

    # Extract trace_id before building the episode (it's not a PodcastEpisode field)
    trace_id = episode_data.pop("trace_id", "")

    episode = PodcastEpisode(**episode_data)
    log(
        f"Processing episode: {episode.title}",
        trace_id=trace_id,
        episode_guid=episode.guid,
    )

    try:
        path = processor.process(episode, trace_id=trace_id)
        return Response(f"Processed: {episode.title} → {path}", status=200)
    except Exception as e:
        log(
            f"Error processing {episode.title}: {e}",
            severity="ERROR",
            trace_id=trace_id,
            episode_guid=episode.guid,
        )
        return Response(f"Error: {e}", status=500)


@app.route("/", methods=["GET"])
def health():
    return Response("OK", status=200)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
