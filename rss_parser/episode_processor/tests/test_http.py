"""Tests for the Flask HTTP layer."""

import json

# FAKE_MODE must be set before importing main (which builds the processor at import time)
import os

os.environ["FAKE_MODE"] = "1"
os.environ["OUTPUT_DIR"] = "/tmp/episode_processor_test"

from main import app


def make_episode_payload(**overrides) -> dict:
    defaults = {
        "title": "Test Episode",
        "description": "A test",
        "guid": "test-guid-http",
        "pub_date": "2026-01-01",
        "mp3_url": "https://example.com/test.mp3",
    }
    defaults.update(overrides)
    return defaults


class TestHTTPEndpoint:
    def setup_method(self):
        self.client = app.test_client()

    def test_health_check(self):
        resp = self.client.get("/")
        assert resp.status_code == 200

    def test_missing_body_returns_400(self):
        resp = self.client.post("/", content_type="application/json")
        assert resp.status_code == 400

    def test_valid_episode_returns_200(self):
        resp = self.client.post(
            "/",
            data=json.dumps(make_episode_payload()),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert b"Processed" in resp.data
