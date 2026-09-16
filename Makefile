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
	@echo "  make smoke          - Run OSRM smoke tests with Dataset V1 GPS"
	@echo "  make clean          - Remove generated files"

setup:
	@echo "Installing Python dependencies..."
	cd backend && pip install -e ".[dev]" -q
	@echo "Setup complete."

validate-data:
	@echo "Running Dataset V1 validation..."
	python3 dataset_v1/validation/validate_dataset.py

prepare-map:
	@echo "Preprocessing OSRM map (requires osrm-extract, osrm-partition, osrm-customize)..."
	@mkdir -p runtime/osrm
	@cp dataset_v1/map/raw/hanoi-baseline.osm.pbf runtime/osrm/
	cd runtime/osrm && osrm-extract -p /usr/local/share/osrm/profiles/car.lua hanoi-baseline.osm.pbf && \
		osrm-partition hanoi-baseline.osrm && \
		osrm-customize hanoi-baseline.osrm && \
		rm -f hanoi-baseline.osm.pbf
	@echo "OSRM preprocessing complete."

up:
	@echo "Starting services..."
	docker compose up -d
	@echo "Waiting for services to be healthy..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then \
			echo "API is healthy."; exit 0; \
		fi; \
		echo "Waiting... ($$i/10)"; \
		sleep 5; \
	done

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && python3 -m pytest tests/ -v

smoke:
	@echo "Running OSRM smoke tests with Dataset V1 GPS..."
	python3 scripts/smoke_test.py

clean:
	@echo "Cleaning generated files..."
	rm -rf runtime/osrm/*.osrm runtime/osrm/*.osrm.*
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
