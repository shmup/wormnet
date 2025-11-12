# wormnet development tasks

# format code with black
format:
    ./format

# lint code with ruff
lint:
    ./lint

# run tests (fast unit tests only)
test *ARGS:
    ./test {{ARGS}}

# run integration tests (slower, uses real sockets)
test-integration:
    pytest tests/test_irc_integration.py -v

# run all tests (unit + integration)
test-all: test test-integration

# run all checks (format, lint, test)
check: format lint test

# run tests for a specific file
test-file FILE:
    ./test {{FILE}}
