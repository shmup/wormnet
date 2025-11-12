# wormnet development tasks

# format code with black
format:
    ./format

# lint code with ruff
lint:
    ./lint

# run tests
test *ARGS:
    ./test {{ARGS}}

# run all checks (format, lint, test)
check: format lint test

# run tests for a specific file
test-file FILE:
    ./test {{FILE}}
