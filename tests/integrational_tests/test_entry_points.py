"""
Every entry point must be able to configure its mappers on its own.

These run in a subprocess on purpose. SQLAlchemy resolves relationship
targets against a process-wide registry, and conftest imports all three
models before any test runs - so an in-process check would pass no
matter which imports the entry point itself is missing, which is
exactly how a broken `python -m src.scripts.populate_db` slipped
through once already.
"""

import subprocess
import sys

import pytest

#: Modules that start a process: the API, the Celery app and its task
#: modules, and the standalone seeding script.
ENTRY_POINTS = [
    "src.main",
    "src.celery_app",
    "src.periodic_tasks",
    "src.video_probe.tasks",
    "src.scripts.populate_db",
]

_CHECK = (
    "import importlib, sys;"
    "importlib.import_module(sys.argv[1]);"
    "from sqlalchemy.orm import configure_mappers;"
    "configure_mappers()"
)


@pytest.mark.parametrize("module", ENTRY_POINTS)
def test_entry_point_configures_mappers(module):
    """Importing the entry point alone must leave the ORM usable."""
    result = subprocess.run(
        [sys.executable, "-c", _CHECK, module],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        f"{module} cannot configure its mappers on its own:\n"
        f"{result.stderr[-1500:]}"
    )
