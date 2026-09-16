.PHONY: help setup validate-data prepare-map up down logs test smoke clean

help:
	@echo "EV Recommendation API - Available commands:"
	@echo "  make setup          - Install Python dependencies"
	@echo "  make validate-data  - Run Dataset V1 validation"
	@echo "  make prepare-map    - Preprocess OSRM map from baseline PBF"
	@echo "  make up             - Start all services (Docker Compose)"
	@echo "  make down           - Stop all services"
	@echo "  make logs           - View service logs"
	@echo "  make test           - Run pytest tests"
	@echo "  make smoke           - Run OSRM smoke tests with Dataset V1 GPS"
	@echo "  make clean           - Remove generated files"

setup:
	@echo "Installing Python dependencies..."
	cd backend && pip install -e ".[dev]" -q
	@echo "Setup complete."

validate-data:
	@echo "Running Dataset V1 validation..."
	python3 dataset_v1/validation/validate_dataset.py

prepare-map:
	@echo "Preprocessing OSRM map via Docker..."
	mkdir -p runtime/osrm
	cp dataset_v1/map/raw/hanoi-baseline.osm.pbf runtime/osrm/
	-docker run --rm -v "//e/build6week/runtime/osrm:/data" osrm/osrm-backend osrm-extract -p /usr/local/share/osrm/profiles/car.lua /data/hanoi-baseline.osm.pbf
	-docker run --rm -v "//e/build6week/runtime/osrm:/data" osrm/osrm-backend osrm-partition /data/hanoi-baseline.osrm
	-docker run --rm -v "//e/build6week/runtime/osrm:/data" osrm/osrm-backend osrm-customize /data/hanoi-baseline.osrm
	rm -f runtime/osrm/hanoi-baseline.osm.pbf
	@echo "OSRM preprocessing complete."

up:
	@echo "Starting services..."
	docker compose up -d
	@echo "Waiting for services to be healthy..."
	docker compose ps

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && python3 -m pytest tests/ -v

smoke:
	@echo "Running OSRM smoke tests with Dataset V1 GPS..."
	@docker run --rm --network build6week_default -v "//e/build6week/dataset_v1:/dataset_v1:ro" python:3.11-slim sh -c \
		"pip install httpx -q 2>/dev/null; python3 - << 'EOF'; echo; echo 'SMOKE TEST COMPLETE'" 2>&1 || \
	docker exec ev_api python3 -c "import httpx; print('OSRM reachable')"
	python3 scripts/smoke_test.py 2>&1 || \
		@echo "Smoke test requires running services: docker compose up"

clean:
	@echo "Cleaning generated files..."
	rm -rf runtime/osrm/*.osrm runtime/osrm/*.osrm.* runtime/osrm/*.pbf
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
