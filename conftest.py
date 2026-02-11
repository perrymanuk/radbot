"""Root conftest.py - excludes ad-hoc test scripts from pytest collection."""

collect_ignore_glob = [
    "tools/test_*.py",
    "tools/*_test.py",
    "examples/test_*.py",
    "examples/*_test.py",
]
