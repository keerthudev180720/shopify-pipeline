"""Raw landing zone writer.

Layout (mirrors the S3 layout we'll use later):
  data/raw/<entity>/date=YYYY-MM-DD/run_<run_id>.jsonl
  data/raw/_runs/run_<run_id>.json          (run summary / audit log)

Rules:
  - Raw is APPEND-ONLY and UNMODIFIED: each line wraps the API record untouched
    in "payload", plus metadata (_run_id, _extracted_at, _entity). Old files are
    never overwritten, which gives us history of every record for free.
  - Files are written to a .tmp path and renamed only when complete, so a crash
    never leaves a half-written file that downstream loaders might pick up.
"""
import json, os
from datetime import datetime, timezone

RAW_ROOT = os.path.join("data", "raw")


class RawWriter:
    def __init__(self, entity, run_id, run_date):
        folder = os.path.join(RAW_ROOT, entity, f"date={run_date}")
        os.makedirs(folder, exist_ok=True)
        self.entity, self.run_id = entity, run_id
        self.final_path = os.path.join(folder, f"run_{run_id}.jsonl")
        self.tmp_path = self.final_path + ".tmp"
        self._f = open(self.tmp_path, "w", encoding="utf-8")
        self.count = 0

    def write(self, record):
        line = {
            "_run_id": self.run_id,
            "_extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "_entity": self.entity,
            "payload": record,
        }
        self._f.write(json.dumps(line) + "\n")
        self.count += 1

    def commit(self):
        """Finish the file atomically. An empty file is still committed: it records
        'ran successfully, nothing changed' (different from 'never ran')."""
        self._f.close()
        os.replace(self.tmp_path, self.final_path)
        return self.final_path

    def abort(self):
        self._f.close()
        if os.path.exists(self.tmp_path):
            os.remove(self.tmp_path)


def write_run_summary(run_id, summary):
    folder = os.path.join(RAW_ROOT, "_runs")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"run_{run_id}.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    return path