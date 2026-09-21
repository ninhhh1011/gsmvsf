.PHONY: setup validate-data prepare-map up down logs test smoke prepare-external-gps validate-external-gps
setup:
	python -m pip install -e "backend[dev]"
validate-data:
	python scripts/validate_frozen_dataset.py
prepare-map:
	docker compose up -d --build graphhopper
up:
	docker compose up -d --build
load-roads:
	python scripts/load_road_network.py
down:
	docker compose down
logs:
	docker compose logs -f
test:
	python -m pytest backend/tests -q --basetemp=runtime/migration/pytest
smoke:
	python scripts/smoke_test.py
	python scripts/smoke_test_week3.py
prepare-external-gps:
	python scripts/prepare_external_gps.py
validate-external-gps:
	python scripts/validate_external_gps.py
