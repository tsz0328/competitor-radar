"""清空账号与名下业务数据，并插入新的管理员账号。

范围（2026-09-20 已对 dev.db 执行过一次，用户确认）：
- 删除：users 全部 + 名下业务数据（竞品/监控源/快照/事件/趋势/周报/抓取日志/已读记录）
- 改归属：llm_providers、app_settings（这两张表里都有真实 LLM Key，改指新 admin 而不是删）
- 保留：alembic_version（迁移状态）、system_settings（0 行历史遗留表）

用法（新账号的邮箱与密码从命令行传入，脚本内不写任何明文凭据）：
    python .codebuddy/reset_accounts.py inventory            # 只看现状，不改数据
    python .codebuddy/reset_accounts.py apply <邮箱> <密码>   # 先备份再执行
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

BASE = r"D:\project\competitor-radar\backend"
DB = os.path.join(BASE, "dev.db")

# 由 main() 从命令行填入；为空直接拒绝执行，防止误跑
NEW_EMAIL = ""
NEW_PASSWORD = ""

# 需要清空的表（按外键依赖：先子后父，虽然 SQLite 外键默认关闭，仍按序更稳妥）
TABLES_TO_CLEAR = [
    "event_reads",
    "trend_insights",
    "page_snapshots",
    "intelligence_events",
    "monitor_sources",
    "crawl_logs",
    "weekly_reports",
    "competitors",
]
# 不删但需要改归属。
# - llm_providers：多供应商配置（含真实 Key）
# - app_settings：按用户一人一行的「全局设置」（LLM 开关 + 旧版单配置兼容字段，
#   里面也存着一条真实 Key）。它本来是「删用户时连带删掉」的（admin.py:301），
#   但用户选的是「密钥不丢」，所以改归属而不是删——否则会留下无主行，
#   新 admin 登录后看不到任何 LLM 配置。
TABLES_TO_REPOINT = ["llm_providers", "app_settings"]
# 明确保留（不删也不改归属）。
# system_settings 是 0 行的历史遗留表——数据清理不顺手改 schema；
# alembic_version 必须保住，否则迁移状态丢失。
TABLES_TO_KEEP = ["alembic_version", "system_settings"]


def tables(conn):
    return [
        r[0]
        for r in conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
        ).fetchall()
    ]


def inventory(conn):
    print("=== 表清单与行数 ===")
    plan = {}
    for t in tables(conn):
        n = conn.execute(f'select count(*) from "{t}"').fetchone()[0]
        if t == "users":
            action = "清空"
        elif t in TABLES_TO_CLEAR:
            action = "清空"
        elif t in TABLES_TO_REPOINT:
            action = "改归新 admin"
        elif t in TABLES_TO_KEEP:
            action = "保留"
        else:
            action = "**未分类**"
        plan[t] = action
        print(f"  {n:>6}  {t:<22} {action}")
    unknown = [t for t, a in plan.items() if a == "**未分类**"]
    if unknown:
        print("\n!! 有未分类的表，先决定它们的处置再执行：", unknown)

    print("\n=== 将被删除的账号 ===")
    for r in conn.execute(
        "select id, username, email, is_admin from users order by id"
    ).fetchall():
        print("   ", r)

    print("\n=== llm_providers（保留，将改指新 admin）===")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(llm_providers)").fetchall()]
    for r in conn.execute("select * from llm_providers").fetchall():
        d = dict(zip(cols, r))
        print(
            f"    id={d.get('id')} user_id={d.get('user_id')} "
            f"name={d.get('name')} model={d.get('model')} "
            f"api_key长度={len(str(d.get('api_key') or ''))} enabled={d.get('enabled')}"
        )

    print("\n=== app_settings（保留，值一律不打印）===")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(app_settings)").fetchall()]
    print("    列：", cols)
    for r in conn.execute("select * from app_settings").fetchall():
        d = dict(zip(cols, r))
        # 只打印「有哪些配置项」与是否已填，绝不打印授权码明文
        print(
            "    "
            + " | ".join(
                f"{k}={'已填(' + str(len(str(v))) + '字符)' if v else '空'}"
                for k, v in d.items()
            )
        )
    return unknown


def apply(conn):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{DB}.bak-{stamp}-before-reset"
    shutil.copy2(DB, bak)
    print("备份 ->", bak, os.path.getsize(bak), "bytes")

    print("\n=== 开始删除 ===")
    for t in TABLES_TO_CLEAR + ["users"]:
        n = conn.execute(f'select count(*) from "{t}"').fetchone()[0]
        conn.execute(f'delete from "{t}"')
        print(f"  清空 {t}: {n} 行")

    print("\n=== 插入新 admin ===")
    # 复用应用的哈希实现，保证与登录校验一致（bcrypt）
    sys.path.insert(0, BASE)
    from app.core.security import hash_password

    cur = conn.execute(
        "insert into users (username, email, nickname, password_hash, "
        "password_length, avatar, is_admin, is_active) "
        "values (?, ?, '', ?, ?, '', 1, 1)",
        (NEW_EMAIL, NEW_EMAIL, hash_password(NEW_PASSWORD), len(NEW_PASSWORD)),
    )
    new_id = cur.lastrowid
    print(f"  id={new_id} username={NEW_EMAIL} email={NEW_EMAIL} is_admin=1")

    print("\n=== llm_providers / app_settings 改归新 admin（仅改 user_id，不动其它列）===")
    for t in TABLES_TO_REPOINT:
        before = conn.execute(f'select user_id from "{t}"').fetchall()
        conn.execute(f'update "{t}" set user_id = ?', (new_id,))
        print(f"  {t}: user_id {sorted({r[0] for r in before})} -> {new_id}")

    conn.commit()

    print("\n=== 执行后核对 ===")
    for t in sorted(tables(conn)):
        n = conn.execute(f'select count(*) from "{t}"').fetchone()[0]
        print(f"  {n:>6}  {t}")
    print()
    for r in conn.execute(
        "select id, username, email, is_admin, is_active, "
        "password_hash is not null from users"
    ).fetchall():
        print("  users:", r)


def main():
    global NEW_EMAIL, NEW_PASSWORD
    mode = sys.argv[1] if len(sys.argv) > 1 else "inventory"
    if mode == "apply":
        if len(sys.argv) < 4 or not sys.argv[2].strip() or not sys.argv[3]:
            print("用法：reset_accounts.py apply <邮箱> <密码>")
            return 2
        NEW_EMAIL, NEW_PASSWORD = sys.argv[2].strip().lower(), sys.argv[3]
        if "@" not in NEW_EMAIL:
            print("邮箱格式不对，已中止。")
            return 2
    # 用原生 sqlite3 直连（不经过应用，避免 ORM 缓存与事件钩子干扰）
    conn = sqlite3.connect(DB)
    try:
        unknown = inventory(conn)
        if mode == "apply":
            if unknown:
                print("\n拒绝执行：存在未分类的表。")
                return 1
            print("\n" + "=" * 60)
            apply(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
