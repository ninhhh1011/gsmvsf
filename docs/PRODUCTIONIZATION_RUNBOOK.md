# Productionization Runbook

**System:** EV Recommendation API
**Version:** Week 5 + Week 6 Productionization
**Last Updated:** 2026-09-22

---

## Service Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Applications                         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI (ev_api)                              │
│  Port: 8000                                                     │
│  Health: /health, /ready                                        │
│  Metrics: /api/v1/metrics                                       │
└─────────────────────────────────────────────────────────────────┘
        │                   │                    │
        ▼                   ▼                    ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ GraphHopper │    │ PostgreSQL  │    │    Redis    │
│ Port: 8989  │    │  Port: 5432 │    │  Port: 6379 │
│ Routing &   │    │ Segments &  │    │ Cache &     │
│ Map Match   │    │ Snapshots   │    │ Driver State│
└─────────────┘    └─────────────┘    └─────────────┘
```

---

## Startup Procedures

### 1. Standard Startup

```bash
cd /path/to/build6week
docker compose up -d
```

Startup order (handled automatically via `depends_on`):
1. PostgreSQL → waits for healthy
2. GraphHopper → waits for healthy (includes graph load ~10min)
3. API → starts when dependencies healthy

### 2. Verify Startup

```bash
# Check service health
curl http://localhost:8000/health
# Expected: {"status":"healthy"}

curl http://localhost:8000/api/v1/readiness
# Expected: {"status":"ready","graphhopper":true,"postgis":true,"redis":true}
```

### 3. First Request Warmup

```bash
curl -X POST http://localhost:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  -d @test_request.json
```

---

## Monitoring

### Prometheus Metrics

```bash
curl http://localhost:8000/api/v1/metrics
```

Key metrics to watch:

| Metric | Alert Threshold | Description |
|--------|-----------------|-------------|
| `ev_recommendation_latency_seconds` | P50 > 500ms | High latency |
| `ev_candidate_state_conflicts_total` | Increasing | State conflicts |
| `ev_db_fallback_total` | Increasing | Cache misses |
| `ev_active_drivers` | > expected | Unusual driver count |

### Health Checks

```bash
# Liveness
curl http://localhost:8000/health

# Readiness
curl http://localhost:8000/ready

# Detailed (check response body)
curl -s http://localhost:8000/ready | jq .
```

---

## Failure Procedures

### A. GraphHopper Failure

**Symptoms:**
- `/ready` returns 503 with `graphhopper: false`
- Recommendation requests fail with `RoutingEngineUnavailableError`

**Recovery:**
```bash
docker compose restart graphhopper
# Wait for healthy (~1 minute)
watch -n5 "curl -s http://localhost:8989/health"
```

**Impact:** All routing and map-matching requests fail until GraphHopper recovers.

---

### B. PostgreSQL Failure

**Symptoms:**
- `/ready` returns 503 with `postgis: false`
- All database operations fail

**Recovery:**
```bash
docker compose restart db
# Wait for healthy
docker compose exec db pg_isready -U postgres
```

**Impact:** All API requests fail until PostgreSQL recovers.

---

### C. Redis Failure

**Symptoms:**
- `/ready` returns with `redis: false`
- Snapshot cache falls back to PostgreSQL (transparent)
- Driver state uses local-only (single-instance behavior)

**Recovery:**
```bash
docker compose restart redis
# Wait for healthy
docker compose exec redis redis-cli ping
```

**Impact:**
- Snapshot cache: Slightly higher latency (DB fallback)
- Driver state: Cross-process sharing disabled (local-only)
- Recommendation: Works with explicit location fallback

---

## Backup & Restore

### PostgreSQL

```bash
# Backup
docker compose exec db pg_dump -U postgres ev_recommendation > backup.sql

# Restore
docker compose exec -T db psql -U postgres ev_recommendation < backup.sql
```

### Redis

**Note:** Redis is configured without persistence by design.

- **Snapshot cache**: Rebuilds from PostgreSQL automatically
- **Driver state**: Non-critical, lost on restart

If Redis data is needed for debugging:
```bash
# Capture current state (before restart)
docker compose exec redis redis-cli KEYS "driver_state:*" > driver_keys.txt
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | postgresql+asyncpg://... | Async database connection |
| `GRAPHHOPPER_BASE_URL` | http://graphhopper:8989 | GraphHopper endpoint |
| `REDIS_URL` | redis://redis:6379/0 | Redis connection |
| `MAX_CONCURRENT_ROUTES` | 4 | Max parallel GraphHopper calls |
| `LOG_LEVEL` | INFO | Logging verbosity |

### Tuning Parameters

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| `max_concurrent_routes` | 4 | 1-32 | GraphHopper parallelism |
| `snapshot_cache_ttl_s` | 60 | 1-3600 | Cache TTL |

---

## Log Analysis

### API Logs

```bash
# View recent logs
docker compose logs --tail=100 api

# Filter by level
docker compose logs --tail=100 api | grep ERROR

# Follow mode
docker compose logs -f api
```

### GraphHopper Logs

```bash
docker compose logs --tail=50 graphhopper
```

---

## Scaling Considerations

### Horizontal Scaling (Multiple API Instances)

1. **Driver State**: Cross-process state is shared via Redis
2. **Configure Redis URL**: Ensure all instances point to same Redis
3. **Load Balancer**: Add nginx/haproxy in front of API instances
4. **Connection Pooling**: Adjust `MAX_CONCURRENT_ROUTES` per instance

### Vertical Scaling (Resource Limits)

For production, add Docker resource limits:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
  graphhopper:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
```

---

## Troubleshooting

### High Latency

1. Check GraphHopper cache status:
```bash
curl http://localhost:8989/health
```

2. Check candidate search metrics:
```bash
curl -s http://localhost:8000/api/v1/metrics | grep candidate_search
```

3. Check database query times:
```bash
docker compose logs api | grep "duration_ms"
```

### State Conflicts

If `ev_candidate_state_conflicts_total` is increasing:

1. Check concurrent requests for same driver
2. Verify Redis connectivity
3. Review request patterns

### Redis Connection Issues

```bash
# Test Redis connectivity
docker compose exec api python -c "import redis; r=redis.from_url('redis://redis:6379'); print(r.ping())"

# Check Redis keys
docker compose exec redis redis-cli KEYS "*" | head -20
```

---

## Shutdown Procedures

### Graceful Shutdown

```bash
# Stop accepting new requests
docker compose stop api

# Wait for in-flight requests to complete (30s default)

# Stop remaining services
docker compose down
```

### Force Shutdown

```bash
docker compose down --remove-orphans
```

---

## Emergency Contacts

*To be filled in with actual on-call contacts*

---

## References

- [Week 6 Documentation](WEEK_6.md)
- [Route Cache Decision](ROUTE_CACHE_DECISION.md)
- [API Documentation](http://localhost:8000/docs)
