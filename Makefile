PYTHON ?= python3
VENV_PYTHON = .venv/bin/python

.PHONY: install run-api run-api-prod seed test test-api demo eval smoke check-db-schema clean-approvals clean-full ui inspect-logs smoke-remote smoke-remote-live verify-hosted-contract verify-env

install:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e .

run-api:
	. .venv/bin/activate && python scripts/run_api.py

run-api-prod:
	. .venv/bin/activate && APP_ENV=production APP_HOST=0.0.0.0 APP_PORT=8000 python scripts/run_api.py

seed:
	. .venv/bin/activate && set -a && . .env.local && set +a && python scripts/seed_domain_data.py

test:
	. .venv/bin/activate && python -m unittest discover -s tests -p 'test_*.py' -v

test-api:
	. .venv/bin/activate && python -m unittest tests.test_api tests.test_demo_flow tests.test_deployment_contract -v

demo:
	. .venv/bin/activate && set -a && . .env.local && set +a && python scripts/demo_queries.py

eval:
	. .venv/bin/activate && set -a && . .env.local && set +a && python3 scripts/run_retrieval_eval.py --mode adapter

smoke:
	. .venv/bin/activate && python scripts/run_retrieval_smoke_test.py

check-db-schema:
	. .venv/bin/activate && set -a && . .env.local && set +a && python scripts/check_db_schema.py

clean-approvals:
	. .venv/bin/activate && set -a && . .env.local && set +a && python -m scripts.cleanup_demo_data --scope approvals --apply

clean-full:
	. .venv/bin/activate && set -a && . .env.local && set +a && python -m scripts.cleanup_demo_data --scope full --apply

ui:
	. .venv/bin/activate && streamlit run ui/app.py

inspect-logs:
	. .venv/bin/activate && python scripts/inspect_logs.py --tail 50

smoke-remote:
	. .venv/bin/activate && set -a && . .env.local && set +a && python scripts/smoke_remote_demo.py

smoke-remote-live:
	. .venv/bin/activate && set -a && . .env.local && set +a && python scripts/smoke_remote_demo.py --timeout 90

verify-hosted-contract:
	. .venv/bin/activate && python -m unittest tests.test_deployment_contract -v

verify-env:
	. .venv/bin/activate && set -a && . .env.local && set +a && python scripts/verify_env.py
