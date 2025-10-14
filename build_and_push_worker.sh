#!/bin/bash
# build and push docker images for worker
# Usage: ./build_and_push_worker.sh <dockerhub_user>
set -e

# Ensure docker buildx is available
if ! docker buildx version >/dev/null 2>&1; then
  echo "Docker Buildx is not available. Please install Docker Buildx and try again."
  exit 1
fi

# Ensure a buildx builder exists and is set as default
if ! docker buildx inspect multiarch-builder >/dev/null 2>&1; then
  docker buildx create --name multiarch-builder --use
else
  docker buildx use multiarch-builder
fi

DOCKERHUB_USER="$1"
if [ -z "$DOCKERHUB_USER" ]; then
  echo "Usage: $0 <dockerhub_user>"
  exit 1
fi

TAG_LATEST=latest
TAG_DATE=$(date +%Y%m%d-%H%M%S)
echo $TAG_DATE

# Worker (multi-arch: linux/amd64, linux/arm64)
docker buildx build --platform linux/amd64,linux/arm64/v8 -f Dockerfile.worker -t $DOCKERHUB_USER/ct-worker:$TAG_LATEST -t $DOCKERHUB_USER/ct-worker:$TAG_DATE --push .

echo "All images built and pushed for platforms: linux/amd64, linux/arm64/v8 with tags: $TAG_LATEST, $TAG_DATE."
