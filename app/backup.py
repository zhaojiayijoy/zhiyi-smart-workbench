"""Consistent SQLite snapshots and explicitly scoped course-file backups."""
from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path

from app import db


def _linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def create_backup(*, project_root: Path, upload_root: Path, export_root: Path,
                  extra_roots: tuple[Path, ...] = ()) -> bytes:
    roots = [("uploads", Path(upload_root).resolve()), ("exports", Path(export_root).resolve()),
             ("projects", Path(project_root).resolve())]
    roots.extend((f"external/{i + 1}", Path(p).resolve()) for i, p in enumerate(extra_roots))
    manifest = {"format_version": 1, "created_at": time.time(), "database_integrity": "ok",
                "roots": {name: str(root) for name, root in roots}, "files": [],
                "consistency": "SQLite snapshot; external files checked individually for concurrent changes"}
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory(prefix="workbench-backup-") as tmp:
        snapshot = Path(tmp) / "workbench.db"
        db.backup_to(snapshot)
        with closing(sqlite3.connect(snapshot)) as conn:
            folders = conn.execute("SELECT folder FROM projects WHERE folder IS NOT NULL AND folder<>''").fetchall()
        for (folder,) in folders:
            path = Path(folder).expanduser()
            if not path.is_absolute():
                path = db.ROOT / path
            path = path.resolve()
            if not any(path.is_relative_to(root) for _, root in roots):
                raise ValueError("存在未授权的课程导出目录，请在 BACKUP_EXTRA_DIRS 中明确配置后重试")
            if not path.is_dir():
                raise ValueError("课程导出目录不存在，无法确认备份完整性")
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
            def add_file(path: Path, name: str) -> None:
                before = path.stat()
                digest = hashlib.sha256()
                with path.open("rb") as source, archive.open(name, "w") as target:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                        target.write(chunk)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("备份期间文件发生变化，请停止生成任务后重试")
                manifest["files"].append({"path": name, "size": after.st_size, "sha256": digest.hexdigest()})

            add_file(snapshot, "workbench.db")
            for name, root in roots:
                if not root.exists():
                    continue
                def on_error(error):
                    raise error
                for current, directories, files in os.walk(root, followlinks=False, onerror=on_error):
                    base = Path(current)
                    for child in directories + files:
                        path = base / child
                        if _linked(path) or not path.resolve().is_relative_to(root):
                            raise ValueError("备份目录含链接或跨目录引用，请移除链接后重试")
                    for filename in sorted(files):
                        path = base / filename
                        if path.resolve() == db.DB_PATH.resolve():
                            continue
                        add_file(path, f"{name}/{path.relative_to(root).as_posix()}")
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return buf.getvalue()
