"""迁移链回归测试：空 SQLite 库必须能一次性升级到 head。

用子进程执行 Alembic，避免测试进程中的 Settings 单例和事件循环污染迁移环境。
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_empty_sqlite_upgrade_reaches_head(tmp_path) -> None:
    db_path = tmp_path / "migration-regression.db"
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "development",
            "DB_URL": f"sqlite+aiosqlite:///{db_path.as_posix()}",
            "DB_AUTO_CREATE": "false",
            "CACHE_BACKEND": "memory",
            "PYTHONUTF8": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, (
        f"alembic upgrade head failed on an empty SQLite database.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    with sqlite3.connect(db_path) as conn:
        version_rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
        assert len(version_rows) == 1
        assert version_rows[0][0] == "20260921_1400"

        models = {
            row[1]: row for row in conn.execute("PRAGMA table_info(llm_providers)").fetchall()
        }
        assert "models" in models
        # SQLite 的 notnull 标志：1 表示迁移确实收紧成了 NOT NULL。
        assert models["models"][3] == 1
