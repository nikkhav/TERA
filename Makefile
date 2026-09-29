DEV_ENV = TERA_ENV_FILE=.env.development UV_CACHE_DIR=.local/uv-cache UV_OFFLINE=1

.PHONY: dev-setup dev-api dev-worker dev-web test

dev-setup:
	test -f .env.development || cp .env.development.example .env.development
	mkdir -p .local
	$(DEV_ENV) uv run alembic upgrade head
	$(DEV_ENV) uv run python -m tera.init_storage

dev-api:
	$(DEV_ENV) uv run uvicorn tera.api:app --reload

dev-worker:
	$(DEV_ENV) uv run python -m tera.worker

dev-web:
	cd frontend && npm run dev

test:
	$(DEV_ENV) uv run ruff check tera tests migrations
	$(DEV_ENV) uv run pytest
	cd frontend && npm run format:check && npm run lint && npm run build
