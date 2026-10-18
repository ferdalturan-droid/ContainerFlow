"""Kør end-to-end-flows mod den lokale app. Se _e2e.py for hvordan."""
import importlib
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _e2e import RESULTS  # noqa: E402

FLOWS = ["b2b", "ownership", "goods", "pricing", "stops", "finish"]

if __name__ == "__main__":
    wanted = sys.argv[1:] or FLOWS
    for name in wanted:
        print(f"== {name}")
        try:
            importlib.import_module(f"flow_{name}").run()
        except Exception:  # noqa: BLE001
            RESULTS["fail"] += 1
            RESULTS["failed"].append(f"{name}: crash")
            traceback.print_exc()
    print(f"\n{RESULTS['pass']} PASS · {RESULTS['fail']} FAIL")
    for f in RESULTS["failed"]:
        print(f"  - {f}")
    sys.exit(1 if RESULTS["fail"] else 0)
