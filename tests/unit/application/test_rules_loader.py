"""``load_all_rules`` must fill the registry completely, on its own (fresh interpreter)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"

SNAPSHOT = """
import json
from seoa.domain.rules import registry
{prelude}
from seoa.application.rules_loader import load_all_rules
load_all_rules()
print(json.dumps({{"rules": sorted(registry.RULES), "messages": sorted(registry.MESSAGES)}}))
"""

IMPORT_EVERYTHING = """
import importlib, pkgutil
import seoa
for m in pkgutil.walk_packages(seoa.__path__, "seoa."):
    importlib.import_module(m.name)
"""


def _snapshot(prelude: str) -> dict[str, list[str]]:
    code = SNAPSHOT.format(prelude=prelude)
    out = subprocess.run(
        [sys.executable, "-c", code],
        env={"PYTHONPATH": str(SRC), "PATH": ""},
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return json.loads(out.stdout)


def test_the_loader_alone_registers_everything_that_importing_every_module_does() -> None:
    alone = _snapshot("")
    everything = _snapshot(IMPORT_EVERYTHING)
    assert alone["rules"] == everything["rules"]
    assert alone["messages"] == everything["messages"]
    assert len(alone["rules"]) > 100  # a sanity floor: the catalogue is not empty
