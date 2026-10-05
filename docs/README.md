# EV Charging & Battery Swap Recommendation System

## Overview
AI-powered recommendation system for electric vehicle charging and battery swap services in Vietnam urban areas.

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Driver    │───▶│  Realtime   │───▶│  Demand     │
│   App       │    │    API      │    │  Detection  │
└─────────────┘    └─────────────┘    └─────────────┘
                                            │
                   ┌─────────────┐          │
                   │  Candidate  │◀─────────┘
                   │   Search    │
                   └─────────────┘
                         │
                         ▼
                   ┌─────────────┐    ┌─────────────┐
                   │  Ranking    │───▶│  Response   │
                   │   Model     │    │   API       │
                   └─────────────┘    └─────────────┘
```

## Quick Start

### Setup
```bash
make setup
make prepare-map
docker compose up -d
```

### Run Tests
```bash
make test
```

### Run Demo
```bash
docker compose up
# Open http://localhost:8000/demo
```

## Components

| Component | Description |
|-----------|-------------|
| Map Matching | GPS → Road segments |
| Demand Detection | SOC evaluation |
| Candidate Search | Station filtering |
| Ranking | ML-based scoring |
| Route History | H3-based route comparison |

## API Documentation

See [API_REFERENCE.md](API_REFERENCE.md)

## Operations

See [OPERATIONS.md](OPERATIONS.md)

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md)
