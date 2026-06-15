.PHONY: gate gate-full gate-release test-fast coreui-build coreui-test lint up

gate:
	python scripts/quality_gate.py --profile minimal

gate-full:
	python scripts/quality_gate.py --profile full --include-advisory

gate-release:
	python scripts/quality_gate.py --profile release --include-advisory

test-fast:
	pytest -q -m fast --maxfail=3

coreui-build:
	cd CoreModules/CoreUI && npm run build

coreui-test:
	cd CoreModules/CoreUI && npm run test -- --run

lint:
	ruff check .

up:
	docker compose up --build
