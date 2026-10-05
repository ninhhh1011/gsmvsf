# API Reference

## Base URL
```
http://localhost:8000/api/v1
```

## Endpoints

### Recommendation

#### POST /recommendation
Get charging/swap recommendation for a driver.

**Request:**
```json
{
  "driver_id": "D001",
  "latitude": 21.0285,
  "longitude": 105.8542,
  "destination_lat": 21.0350,
  "destination_lng": 105.8620,
  "soc_percent": 25.0
}
```

**Response:**
```json
{
  "recommendation": {
    "station_id": "S012",
    "service_type": "CHARGING",
    "eta_minutes": 8.5,
    "distance_km": 2.3
  }
}
```

### Route History

#### POST /routes/compare
Compare two routes using H3 signature.

**Request:**
```json
{
  "route_a": {
    "route_id": "ROUTE_A",
    "coordinates": [[21.028, 105.854], [21.030, 105.856]]
  },
  "route_b": {
    "route_id": "ROUTE_B",
    "coordinates": [[21.028, 105.854], [21.031, 105.857]]
  },
  "resolution": 10
}
```

**Response:**
```json
{
  "shared_h3_cells": 5,
  "total_h3_route_a": 10,
  "total_h3_route_b": 8,
  "adherence_percentage": 62.5,
  "symmetric_similarity": 55.6
}
```

### Health

#### GET /health/live
Kubernetes liveness probe.

#### GET /health/ready
Kubernetes readiness probe (checks dependencies).

#### GET /metrics
Prometheus metrics endpoint.
