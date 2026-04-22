PYTHON ?= python3
VENV_PYTHON = .venv/bin/python

.PHONY: install run-api seed test demo eval smoke clean-approvals clean-full

install:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e .

run-api:
	. .venv/bin/activate && python scripts/run_api.py

seed:
	. .venv/bin/activate && set -a && . .env.local && set +a && python scripts/seed_domain_data.py

test:
	. .venv/bin/activate && python -m unittest discover -s tests -p 'test_*.py' -v

demo:
	. .venv/bin/activate && set -a && . .env.local && set +a && python scripts/demo_queries.py

eval:
	. .venv/bin/activate && set -a && . .env.local && set +a && python3 scripts/run_retrieval_eval.py --mode adapter

smoke:
	. .venv/bin/activate && python scripts/run_retrieval_smoke_test.py

clean-approvals:
	. .venv/bin/activate && set -a && . .env.local && set +a && python -m scripts.cleanup_demo_data --scope approvals --apply

clean-full:
	. .venv/bin/activate && set -a && . .env.local && set +a && python -m scripts.cleanup_demo_data --scope full --apply
