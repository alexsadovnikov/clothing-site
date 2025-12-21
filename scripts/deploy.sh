#!/usr/bin/env bash
set -euo pipefail

cd /srv/clothing-site
git pull --rebase
docker compose up -d --build
docker compose ps
