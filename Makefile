.PHONY: up down logs ingest verify demo audit
up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=150

ingest:
	docker compose run --rm -e INGEST_RUN_ONCE=true ingestion-runner python runner.py

verify:
	python scripts/verify_project.py

demo:
	python scripts/demo_validation.py

audit:
	./security/audit.sh
