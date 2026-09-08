from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "runtime" / "assets" / "characters" / "shenshen"
VIDEO_ROOT = ASSET_ROOT / "videos"
OUTPUT = ASSET_ROOT / "asset-inventory.json"
NEW_RANDOM = {
    "碎碎念-发呆碎碎念.webm",
    "碎碎念-对屏碎碎念.webm",
    "碎碎念-擦桌碎碎念.webm",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_for(relative: str) -> dict[str, str | None]:
    name = Path(relative).name
    if relative.startswith("events/") or name in NEW_RANDOM:
        return {
            "repository": "https://github.com/MerZlin/dsh-pet-indesktop",
            "commit": "8a8a8ae2",
        }
    return {
        "repository": "https://github.com/PC2005-cloud/dsh-pet",
        "commit": None,
    }


def category_for(relative: str) -> str:
    parts = Path(relative).parts
    if parts[:2] == ("events", "work"):
        return "work"
    if parts[:2] == ("events", "balance"):
        return "balance"
    return parts[0]


def main() -> int:
    files = []
    counts: dict[str, int] = {}
    for path in sorted(VIDEO_ROOT.rglob("*.webm"), key=lambda item: item.as_posix()):
        relative = path.relative_to(VIDEO_ROOT).as_posix()
        category = category_for(relative)
        counts[category] = counts.get(category, 0) + 1
        files.append({
            "path": f"videos/{relative}",
            "category": category,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "source": source_for(relative),
        })
    payload = {
        "schemaVersion": 1,
        "character": "shenshen",
        "animationCount": len(files),
        "categoryCounts": dict(sorted(counts.items())),
        "provenance": {
            "legacyAnimations": "91 files imported from PC2005-cloud/dsh-pet; the historical snapshot did not record an upstream commit.",
            "runtimeSyncAnimations": "15 files imported from MerZlin/dsh-pet-indesktop@8a8a8ae2.",
        },
        "files": files,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(files)} animations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
