# AI Runtime Architecture (Infra)
As of: 2026-01-27

## DNS / TLS / Edge
- `voicecrm.online` → RU VPS (Nginx + Let’s Encrypt)
- `ai.voicecrm.online` → EU VPS (Caddy + TLS)

## RU VPS (voicecrm.online) — ports bound to 127.0.0.1
- API: `127.0.0.1:8001` (container `clothing-api`)
- DB: `127.0.0.1:5432` (container `clothing-db`)
- Redis: `127.0.0.1:6379` (container `clothing-redis`)
- MinIO S3: `127.0.0.1:9100` (container `clothing-minio`)
- MinIO console: `127.0.0.1:9101`
- MeiliSearch: `127.0.0.1:7700`

## EU VPS (ai.voicecrm.online)
- Gateway container listens `0.0.0.0:8080`
- Host binds: `127.0.0.1:8080:8080`
- Public exposure via Caddy → `https://ai.voicecrm.online/*`

## Internal networking (RU docker)
All RU containers communicate via `clothing-site_default` network:
- api ↔ db/redis/minio/meili
- worker ↔ api (AI_INTERNAL_URL=http://api:8001)

## Security rule
- No service binds to `0.0.0.0` except web edge (Nginx/Caddy).
- All infra ports are loopback-only, externally reachable only via reverse proxy.
