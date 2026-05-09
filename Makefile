.PHONY: doctor current steward dogfood smoke sanitize

doctor:
	./bin/doctor.sh

current:
	./bin/current-state.sh example-app

steward:
	./bin/steward.sh --project example-app --no-model

dogfood:
	./bin/dogfood-smoke.sh

smoke:
	python3 -m py_compile bin/council.py bin/steward.py
	bash -n bin/session.sh bin/doctor.sh bin/current-state.sh bin/query.sh bin/steward.sh bin/dogfood-smoke.sh bin/sanitize-check.sh
	./bin/current-state.sh example-app
	./bin/query.sh tree example-app
	./bin/dogfood-smoke.sh
	./bin/doctor.sh

sanitize:
	./bin/sanitize-check.sh
