"""Watermark store: remembers, per entity, the upper bound of the last SUCCESSFUL run.

Stored in extractor_state.json, e.g. {"orders": "2026-10-05T03:00:00Z", ...}
Writes are atomic (write temp file, then rename) so a crash can never leave a
half-written state file.
"""
import json, os

STATE_PATH = "extractor_state.json"


def _load():
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH) as f:
        return json.load(f)


def get_watermark(entity):
    return _load().get(entity)


def set_watermark(entity, value):
    data = _load()
    data[entity] = value
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, STATE_PATH)   # atomic on Windows and Linux