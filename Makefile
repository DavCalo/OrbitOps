.PHONY: alarm-demo bootstrap build clean configure integration link-demo package profile-demo python-tests quality session-demo test verify

PYTHON ?= python3
CMAKE ?= cmake
BUILD_DIR ?= build
CMAKE_BUILD_TYPE ?= Release

bootstrap:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

configure:
	$(CMAKE) -S onboard -B $(BUILD_DIR) \
		-DCMAKE_BUILD_TYPE=$(CMAKE_BUILD_TYPE) \
		-DORBITOPS_WARNINGS_AS_ERRORS=ON

build: configure
	$(CMAKE) --build $(BUILD_DIR) --config $(CMAKE_BUILD_TYPE)

python-tests:
	$(PYTHON) -m unittest discover -s tests -v

test: build python-tests
	ctest --test-dir $(BUILD_DIR) --output-on-failure -C $(CMAKE_BUILD_TYPE)

integration: build
	$(PYTHON) scripts/integration_check.py ./$(BUILD_DIR)/orbitops_sim
	$(PYTHON) scripts/link_integration_check.py ./$(BUILD_DIR)/orbitops_sim
	$(PYTHON) scripts/link_demo_check.py ./$(BUILD_DIR)/orbitops_sim
	$(PYTHON) scripts/profile_demo_check.py ./$(BUILD_DIR)/orbitops_sim
	$(PYTHON) scripts/alarm_demo_check.py ./$(BUILD_DIR)/orbitops_sim
	$(PYTHON) scripts/session_demo_check.py ./$(BUILD_DIR)/orbitops_sim

link-demo: build
	$(PYTHON) scripts/link_demo_check.py ./$(BUILD_DIR)/orbitops_sim

profile-demo: build
	$(PYTHON) scripts/profile_demo_check.py ./$(BUILD_DIR)/orbitops_sim

alarm-demo: build
	$(PYTHON) scripts/alarm_demo_check.py ./$(BUILD_DIR)/orbitops_sim

session-demo: build
	$(PYTHON) scripts/session_demo_check.py ./$(BUILD_DIR)/orbitops_sim

quality:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m mypy ground_station tests scripts
	$(PYTHON) -m coverage erase
	$(PYTHON) -m coverage run -m unittest discover -s tests -v
	$(PYTHON) -m coverage report

package:
	rm -rf dist
	$(PYTHON) -m build
	$(PYTHON) scripts/profile_package_check.py
	$(PYTHON) scripts/alarm_policy_package_check.py
	$(PYTHON) scripts/alarm_event_package_check.py
	$(PYTHON) scripts/session_inspection_package_check.py

verify: quality test integration package

clean:
	rm -rf $(BUILD_DIR) dist .coverage .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
