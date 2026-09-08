"""Pytest bootstrap: isolate the SQLite database for the test run."""
import os
import tempfile

os.environ.setdefault(
    "DIFFEQ_DB",
    os.path.join(tempfile.mkdtemp(prefix="diffeq-tests-"), "app.db"),
)