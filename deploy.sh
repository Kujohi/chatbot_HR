#!/usr/bin/env bash
set -e

# rebuild docker

docker buildx build --platform linux/amd64 \
  -t kujohi1102/menas_hr_bot:latest \
  --push .