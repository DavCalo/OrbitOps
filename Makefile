.PHONY: build test integration clean

BUILD_DIR ?= build

build:
	cmake -S onboard -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=Release
	cmake --build $(BUILD_DIR)

test: build
	python3 -m unittest discover -s tests -v
	ctest --test-dir $(BUILD_DIR) --output-on-failure

integration: build
	python3 scripts/integration_check.py ./$(BUILD_DIR)/orbitops_sim

clean:
	rm -rf $(BUILD_DIR)
