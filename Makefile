.PHONY: doctor current steward warden stats board dogfood smoke sanitize

doctor:
	./bin/doctor.sh

current:
	./bin/current-state.sh example-app

steward:
	./bin/steward.sh --project example-app --no-model

warden:
	./bin/warden.sh

stats:
	./bin/query.sh stats

board:
	./bin/query.sh board

dogfood:
	./bin/dogfood-smoke.sh

smoke:
	python3 -m py_compile bin/council.py bin/steward.py
	bash -n bin/session.sh bin/doctor.sh bin/current-state.sh bin/query.sh bin/steward.sh bin/traffic.sh bin/warden.sh bin/rotate-ledger.sh bin/install-hooks.sh bin/dogfood-smoke.sh bin/sanitize-check.sh hooks/pre-push
	./bin/current-state.sh example-app
	./bin/query.sh tree example-app
	./bin/dogfood-smoke.sh
	./bin/doctor.sh

sanitize:
	./bin/sanitize-check.sh
