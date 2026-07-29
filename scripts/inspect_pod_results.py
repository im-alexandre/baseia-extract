from __future__ import annotations

import hashlib
import json
from pathlib import Path


def main() -> None:
    root = Path("/workspace/results/tasks")
    records = []
    if root.is_dir():
        for task_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            manifest_path = task_dir / "manifest.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest = {}
            files = sorted(path for path in task_dir.rglob("*") if path.is_file())
            middle_files = [
                path
                for path in files
                if path.name.casefold().endswith("_middle.json")
            ]
            records.append(
                {
                    "task_id": task_dir.name,
                    "status": manifest.get("status"),
                    "correlation_key": manifest.get("correlation_key"),
                    "persisted_at": manifest.get("persisted_at"),
                    "file_count": len(files),
                    "bytes": sum(path.stat().st_size for path in files),
                    "middle_files": [
                        {
                            "path": str(path.relative_to(task_dir)).replace("\\", "/"),
                            "bytes": path.stat().st_size,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        }
                        for path in middle_files
                    ],
                }
            )
    print(
        json.dumps(
            {
                "root": str(root),
                "task_count": len(records),
                "tasks": records,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
