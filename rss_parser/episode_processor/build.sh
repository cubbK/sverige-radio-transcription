#!/bin/bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-dan-learning-0929}"
REGION="${REGION:-europe-west1}"
REPO="episode-processor"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/episode-processor"

echo "==> Building ${IMAGE}:latest"

# Ensure Docker can push to Artifact Registry
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Build for linux/amd64 (Cloud Run target)
docker build --platform linux/amd64 -t "${IMAGE}:latest" .

# Push
docker push "${IMAGE}:latest"

echo "==> Done. Image pushed to ${IMAGE}:latest"
