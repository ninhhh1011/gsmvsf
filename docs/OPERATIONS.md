# Operations Guide

## Local deployment

Run the stack on one Docker host:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
```

All published ports bind to `127.0.0.1`: PostgreSQL 5432, Redis 6379, GraphHopper 8989, API ports 8000 and 8002, and frontend 3000. The two API containers share one PostgreSQL, Redis, and GraphHopper instance. The data plane is single-node; this setup does not provide host-level failover.

## Checks

```bash
make lint
make test
make validate-data
```

The metrics endpoint is `/metrics`. Readiness is `/readiness`. Runtime dependencies are PostgreSQL, optional Redis cache, and GraphHopper; dependency failures are reported explicitly.

## Maintenance

Use the repository's migration and dataset validation scripts. Dataset V1 is canonical and read-only. Keep generated reports under `runtime/`, never in `dataset_v1/`.
