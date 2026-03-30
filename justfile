default:
    @just --list

test:
    pytest

lint:
    ruff check src tests

format:
    ruff format src tests

typecheck:
    mypy src/

verify:
    just lint
    just test
