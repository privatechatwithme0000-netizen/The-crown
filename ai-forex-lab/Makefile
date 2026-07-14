.PHONY: help install lint typecheck test check fmt up down migrate revision

help:
	@echo "install    - install package with dev extras (editable)"
	@echo "lint       - ruff check"
	@echo "fmt        - ruff format + fix"
	@echo "typecheck  - mypy --strict"
	@echo "test       - pytest"
	@echo "check      - lint + typecheck + test"
	@echo "up/down    - docker compose up/down"
	@echo "migrate    - alembic upgrade head"

install:
	pip install -e ".[dev]"

lint:
	ruff check src tests

fmt:
	ruff format src tests
	ruff check --fix src tests

typecheck:
	mypy

test:
	pytest

check: lint typecheck test

up:
	docker compose up --build

down:
	docker compose down

migrate:
	alembic upgrade head

revision:
	alembic revision -m "$(m)"
