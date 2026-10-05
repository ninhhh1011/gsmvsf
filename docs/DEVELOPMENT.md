# Development Guide

## Setup

### Prerequisites
- Python 3.10+
- Docker
- PostgreSQL
- Redis

### Install
```bash
make setup
make prepare-map
```

### Run Tests
```bash
make test
```

### Run Demo
```bash
make up
# Open http://localhost:8000/demo
```

## Project Structure

```
backend/
├── app/
│   ├── api/v1/          # API endpoints
│   ├── core/             # Core utilities
│   ├── models/           # Data models
│   └── services/         # Business logic
│       ├── candidate/    # Week 3
│       ├── demand/      # Week 2
│       ├── map_matching/ # Week 1
│       ├── ranking/     # Week 4
│       ├── realtime/    # Week 5
│       └── route_history/ # Scale Up
├── tests/               # Test files
└── scripts/            # Utility scripts
```

## Testing

### Unit Tests
```bash
pytest backend/tests -v
```

### Integration Tests
```bash
pytest backend/tests/integration -v
```

### Load Tests
```bash
locust -f tests/load/locustfile.py
```

## Code Style

- Follow PEP 8
- Use type hints
- Write docstrings
- Max line length: 100
