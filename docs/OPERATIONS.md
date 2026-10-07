# Operations Guide

## Deployment

### Docker Compose
```bash
docker compose up -d
```

No Kubernetes deployment is currently configured.

## Monitoring

### Prometheus
- Metrics endpoint: `/metrics`
- Alerts: `app/monitoring/alerts.yml`

### Grafana
- Dashboard ID: TBD
- Default credentials: admin/admin

## Troubleshooting

### High Latency
1. Check GraphHopper health
2. Check Redis cache hit rate
3. Review Prometheus metrics

### Service Down
1. Check Docker status: `docker compose ps`
2. Review logs: `docker compose logs`
3. Check external dependencies (PostgreSQL, Redis, GraphHopper)

## Maintenance

### Database Backup
```bash
pg_dump -U postgres ev_recommendation > backup.sql
```

### Clear Cache
```bash
redis-cli FLUSHDB
```

## SLAs

| Metric | Target |
|--------|--------|
| P95 Latency | < 2s |
| Error Rate | < 1% |
| Availability | 99.5% |
