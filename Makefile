PYTHON ?= python
VENV_DIR ?= .venv
COMPOSE ?= docker compose

ifeq ($(OS),Windows_NT)
VENV_PYTHON := $(VENV_DIR)/Scripts/python.exe
else
VENV_PYTHON := $(VENV_DIR)/bin/python
endif

.PHONY: start run demo seed-demo clean down test install-requirements format check help

help:
	@echo "Available targets:"
	@echo "  make start                - create .venv, install requirements, create .env"
	@echo "  make install-requirements - install Python dependencies into .venv"
	@echo "  make run                  - reset volumes and run clean project via docker compose up --build"
	@echo "  make demo                 - reset volumes, start stack in background and seed demo data"
	@echo "  make seed-demo            - seed demo candidates/vacancies into running stack"
	@echo "  make clean                - stop stack and remove volumes"
	@echo "  make down                 - stop stack without removing volumes"
	@echo "  make test                 - run pytest using .venv"
	@echo "  make format               - format code with black"
	@echo "  make check                - check code style against PEP8 (pycodestyle)"

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV_DIR)

.env:
	$(PYTHON) -c "from pathlib import Path; env = Path('.env'); example = Path('.env.example'); text = example.read_text(encoding='utf-8') if example.exists() else '# Auto-generated .env\\nLOG_LEVEL=INFO\\n'; env.write_text(text, encoding='utf-8'); print('Created .env from .env.example' if example.exists() else 'Created minimal .env')"

install-requirements: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements.txt

start: .env install-requirements
	@echo "Project bootstrap completed"

run: .env
	$(COMPOSE) down --volumes --remove-orphans
	$(COMPOSE) up --build

demo: .env
	$(COMPOSE) down --volumes --remove-orphans
	$(COMPOSE) up --build
	$(COMPOSE) exec -T profile python -m scripts.seed_demo_data
	@echo "Demo data is loaded. Open http://localhost:3000"

seed-demo: .env
	$(COMPOSE) up -d
	$(COMPOSE) exec -T profile python -m scripts.seed_demo_data

clean:
	$(COMPOSE) down --volumes --remove-orphans

down:
	$(COMPOSE) down

test: install-requirements
	$(VENV_PYTHON) -m pytest -q

format: install-requirements
	$(VENV_PYTHON) -m black .

check: install-requirements
	$(VENV_PYTHON) -m pycodestyle --max-line-length=88 common gateway matching profile search scripts conftest.py
