.PHONY: setup validate-data prepare-map up down logs test test-backend test-frontend test-all lint lint-fix smoke prepare-external-gps validate-external-gps load-snapshots evaluate-week4 verify-week4 benchmark-route-familiarity migrate-route-familiarity rollback-route-familiarity ci-check
setup:
	python -m pip install -e "backend[dev]"
validate-data:
	python -B scripts/validate_frozen_dataset.py
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
test: test-backend test-frontend
test-backend:
	python -B -m pytest backend/tests -q --basetemp=runtime/migration/pytest
test-frontend:
	node --test tests/frontend/*.mjs
test-all: test-backend test-frontend validate-data
lint:
	ruff check backend
smoke:
	python scripts/smoke_test.py
	python scripts/smoke_test_week3.py
prepare-external-gps:
	python scripts/prepare_external_gps.py
validate-external-gps:
	python scripts/validate_external_gps.py
load-snapshots:
	python -B scripts/load_week4_snapshots.py
evaluate-week4:
	python -B scripts/evaluate_week4.py
verify-week4:
	python -B scripts/verify_week4.py
benchmark-route-familiarity:
	python -B -m scripts.benchmark_route_familiarity --output docs/reports/phase4-route-familiarity-benchmark.json
migrate-route-familiarity:
	python -B -m scripts.migrate_route_familiarity
rollback-route-familiarity:
	python -B -m scripts.migrate_route_familiarity --rollback
ci-check: lint test-backend test-frontend validate-data
