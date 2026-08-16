# Deployment Guide

## Local Development (Docker Compose)

```bash
# 1. Clone and copy env
git clone <repo>
cd urban-air-quality
cp .env.example .env

# 2. Start all services
docker compose up -d

# 3. Check health (wait ~60s for seeding)
curl http://localhost:8000/health

# 4. Access
# Frontend:  http://localhost:3000
# API docs:  http://localhost:8000/docs
# RedisInsight (optional): localhost:6379
```

## Environment Variables

All variables with defaults — platform runs without any external API keys:

```bash
# Required for production (change these)
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
POSTGRES_PASSWORD=<strong-password>

# Optional — enables real data sources
ANTHROPIC_API_KEY=      # AI assistant (console.anthropic.com — free tier)
OPENAQ_API_KEY=         # Real CAAQMS data (explore.openaq.org — free)
NEXT_PUBLIC_MAPBOX_TOKEN=  # Map rendering (account.mapbox.com — free 50k/month)
```

## Production Deployment (AWS India / Azure India / NIC)

### Prerequisites
- Docker + Docker Compose v2
- Domain with SSL certificate
- Minimum: 4 vCPU, 8GB RAM, 100GB SSD

### Steps

```bash
# 1. Set production env
cp .env.example .env.production
# Edit .env.production — set ENVIRONMENT=production, strong SECRET_KEY, DB passwords

# 2. Deploy
docker compose --env-file .env.production up -d --build

# 3. Run migrations explicitly
docker compose exec backend alembic upgrade head

# 4. Verify
docker compose ps
curl https://your-domain.gov.in/health
```

### Nginx reverse proxy (recommended)

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.gov.in;

    ssl_certificate /etc/letsencrypt/live/your-domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain/privkey.pem;

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }

    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
    }
}
```

### Database backup

```bash
# Backup
docker compose exec db pg_dump -U airuser airquality | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore
gunzip -c backup_20240101.sql.gz | docker compose exec -T db psql -U airuser airquality
```

## Scaling

- **Horizontal backend scaling**: run multiple `backend` replicas behind a load balancer; all state is in DB + Redis
- **Celery workers**: scale `celery_worker` replicas independently
- **Read replicas**: TimescaleDB supports streaming replication; point analytics queries at replica
- **CDN**: serve Next.js static assets from CloudFront/Azure CDN

## Monitoring

Health endpoint: `GET /health` returns JSON with database and Redis status.

For production observability:
- Structured JSON logs → CloudWatch / Azure Monitor / ELK
- Prometheus metrics available at `/metrics` (add `prometheus-fastapi-instrumentator`)
- Celery task monitoring: Flower (`celery -A app.workers.celery_app flower`)
