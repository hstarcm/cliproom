.PHONY: test up down logs

# Single command for all suites (AC14). Portable twin: scripts/test.sh
test:
	bash scripts/test.sh

# Full stack with one command (AC13)
up:
	docker compose up --build -d
	@echo "frontend:    http://localhost:8080"
	@echo "grafana:     http://localhost:3300"
	@echo "mailpit:     http://localhost:8025"
	@echo "prometheus:  http://localhost:9090  alertmanager: http://localhost:9093"

down:
	docker compose down -v

logs:
	docker compose logs -f api
