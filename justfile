# wormnet development tasks

# format code with black
format:
    uv run --with black black wormnet tests wormnet.py

# lint code with ruff
lint:
    uv run --with ruff ruff check wormnet tests wormnet.py

# run tests (fast unit tests only)
test *ARGS:
    uv run --with pytest --with flask --with tomli --with requests pytest tests/ -v --ignore=tests/test_irc_integration.py {{ARGS}}

# run integration tests (slower, uses real sockets)
test-integration:
    uv run --with pytest --with flask --with tomli --with requests pytest tests/test_irc_integration.py -v

# run all tests (unit + integration)
test-all: test test-integration

# run all checks (format, lint, test)
check: format lint test
