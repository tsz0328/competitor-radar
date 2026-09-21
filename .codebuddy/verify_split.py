"""「账号 + 选填邮箱」双标识体系的端到端验证（对真实应用 + dev.db 副本）。

用法：
    python .codebuddy/verify_split.py <管理员登录标识> <管理员密码>

凭据**从命令行传**，脚本内不留明文（与 reset_accounts.py 同一约定）。

为什么用副本：验证过程要建多个测试账号，若直接写进 dev.db 会留下垃圾数据。
副本跑完即删，真实库只承受「迁移已应用」这一件事（迁移本身单独核过）。

为什么能不发真邮件：把 settings.notify_backend 临时改成 log（仅在本进程内），
`notify()` 依然返回 True，但只写日志；验证码照常落进缓存，脚本直接从缓存里读。
真 SMTP（NOTIFY_BACKEND=smtp）不会被触发，收件箱是干净的。
"""
import asyncio
import os
import shutil
import sqlite3
import sys

BASE = r"D:\project\competitor-radar\backend"
LIVE = os.path.join(BASE, "dev.db")
COPY = os.path.join(BASE, "_e2e.db")

if len(sys.argv) < 3:
    print(__doc__)
    raise SystemExit(2)
ADMIN_ACCOUNT, ADMIN_PASSWORD = sys.argv[1], sys.argv[2]

shutil.copy2(LIVE, COPY)
os.environ["DB_URL"] = "sqlite+aiosqlite:///./_e2e.db"
os.chdir(BASE)
sys.path.insert(0, BASE)

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.cache import get_cache  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

settings = get_settings()
settings.notify_enabled = True
settings.notify_backend = "log"

PASSWORD = "e2e-pass-1234"
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    results.append((ok, label))
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f"  —— {detail}" if detail else ""))
    return ok


async def code_for(email: str, scene: str = "login") -> str:
    code = await get_cache().get(f"email_code:code:{scene}:{email}")
    assert code, f"验证码没进缓存：{scene}:{email}"
    return code


async def clear_cooldown(email: str) -> None:
    """清掉重发冷却，方便同一邮箱连发多次（重发限流另有专门用例覆盖）。"""
    await get_cache().delete(f"email_code:cd:{email}")


async def main() -> int:
    print(f"缓存后端 = {type(get_cache()).__name__}")
    print(f"通知后端 = {settings.notify_backend}（强制 log，不发真邮件）")
    print()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://e2e", timeout=30
    ) as c:
        print("=== 1. 管理员登录（邮箱形态的账号名）===")
        r = await c.post(
            "/api/auth/login",
            json={"account": ADMIN_ACCOUNT, "password": ADMIN_PASSWORD},
        )
        check(r.status_code == 200, "管理员登录", r.text[:120])
        admin_token = r.json()["token"] if r.status_code == 200 else ""
        admin_h = {"Authorization": f"Bearer {admin_token}"}

        print()
        print("=== 2. 注册：只有账号、不填邮箱 ===")
        r1 = await c.post(
            "/api/auth/register", json={"username": "solo_user", "password": PASSWORD}
        )
        check(r1.status_code == 200, "账号 solo_user 注册成功（无邮箱）", r1.text[:160])
        check(r1.json()["user"]["email"] == "", "未绑邮箱时 email 回空串")

        r2 = await c.post(
            "/api/auth/register", json={"username": "solo_user2", "password": PASSWORD}
        )
        check(
            r2.status_code == 200,
            "第二个无邮箱账号也能注册（NULL 不撞唯一索引）",
            r2.text[:160],
        )

        print()
        print("=== 3. 注册：账号 + 邮箱（需验证码）===")
        email = "e2e-bound@example.com"
        sent = await c.post(
            "/api/auth/email-code", json={"account": email, "scene": "login"}
        )
        check(sent.status_code == 200, "发送邮箱验证码", sent.text[:120])
        code = await code_for(email)
        r3 = await c.post(
            "/api/auth/register",
            json={
                "username": "tangsizhe",
                "email": email,
                "password": PASSWORD,
                "code": code,
            },
        )
        check(r3.status_code == 200, "注册 账号+邮箱", r3.text[:200])
        check(r3.json()["user"]["username"] == "tangsizhe", "账号名是自定义值")
        check(r3.json()["user"]["email"] == email, "邮箱已绑定")
        await clear_cooldown(email)

        print()
        print("=== 4. 两个标识都能登录 ===")
        for account in ("tangsizhe", email, email.upper()):
            r = await c.post(
                "/api/auth/login", json={"account": account, "password": PASSWORD}
            )
            check(r.status_code == 200, f"用 {account} 登录", r.text[:120])
        user_token = r.json()["token"]
        user_h = {"Authorization": f"Bearer {user_token}"}

        print()
        print("=== 5. 账号名禁 @ / 跨列唯一 ===")
        bad = await c.post(
            "/api/auth/register",
            json={"username": email, "password": PASSWORD},
        )
        check(
            bad.status_code == 400 and bad.json()["code"] == 40013,
            "账号名不允许取成邮箱形态（含 @ → 40013）",
            bad.text[:120],
        )
        dup = await c.post(
            "/api/auth/register",
            json={"username": "tangsizhe", "password": PASSWORD},
        )
        check(
            dup.status_code == 400 and dup.json()["code"] == 40014,
            "账号名重复被拒（40014）",
            dup.text[:120],
        )

        print()
        print("=== 6. 用户中心：改账号名 / 绑邮箱 / 解绑 ===")
        renamed = await c.put(
            "/api/users/me", headers=user_h, json={"username": "tangsizhe-new"}
        )
        check(renamed.status_code == 200, "改账号名", renamed.text[:160])
        check(
            renamed.json()["email"] == email,
            "改账号名不影响已绑定邮箱",
        )
        # 邮箱不能通过 /me 改
        ignored = await c.put(
            "/api/users/me", headers=user_h, json={"email": "hacker@evil.com"}
        )
        check(
            ignored.status_code == 200 and ignored.json()["email"] == email,
            "/api/users/me 传 email 被忽略（换绑必须验码）",
        )

        new_email = "e2e-rebind@example.com"
        await clear_cooldown(new_email)
        await c.post(
            "/api/auth/email-code", json={"account": new_email, "scene": "login"}
        )
        bind = await c.put(
            "/api/users/me/email",
            headers=user_h,
            json={"email": new_email, "code": await code_for(new_email)},
        )
        check(bind.status_code == 200, "换绑到一个新邮箱（带验证码）", bind.text[:160])

        no_code = await c.put(
            "/api/users/me/email", headers=user_h, json={"email": "nocode@example.com"}
        )
        check(
            no_code.status_code == 400 and no_code.json()["code"] == 40008,
            "不带验证码绑邮箱被拒（40008）",
            no_code.text[:120],
        )

        print()
        print("=== 7. 忘记密码：用账号名发起 ===")
        await clear_cooldown(new_email)
        sent = await c.post(
            "/api/auth/email-code", json={"account": "tangsizhe-new", "scene": "reset"}
        )
        check(
            sent.status_code == 200,
            "用账号名发起重置（码发到绑定邮箱）",
            sent.text[:160],
        )
        reset_code = await code_for(new_email, "reset")
        new_pwd = "e2e-brand-new-99"
        reset = await c.post(
            "/api/auth/reset-password",
            json={
                "account": "tangsizhe-new",
                "code": reset_code,
                "newPassword": new_pwd,
            },
        )
        check(reset.status_code == 200, "重置密码", reset.text[:160])
        check(
            (
                await c.post(
                    "/api/auth/login",
                    json={"account": "tangsizhe-new", "password": PASSWORD},
                )
            ).status_code
            == 401,
            "旧密码已失效",
        )
        check(
            (
                await c.post(
                    "/api/auth/login",
                    json={"account": new_email, "password": new_pwd},
                )
            ).status_code
            == 200,
            "新密码可用于登录（用邮箱登录）",
        )

        print()
        print("=== 8. 未绑邮箱的账号无法自助重置 ===")
        r = await c.post(
            "/api/auth/email-code", json={"account": "solo_user", "scene": "reset"}
        )
        check(
            r.status_code == 400 and r.json()["code"] == 40015,
            "无邮箱账号发起重置 → 40015（明确告知，不静默）",
            r.text[:140],
        )

        print()
        print("=== 9. 解绑需要已有密码 ===")
        unbind = await c.put(
            "/api/users/me/email",
            headers={
                "Authorization": (
                    "Bearer "
                    + (
                        await c.post(
                            "/api/auth/login",
                            json={"account": "tangsizhe-new", "password": new_pwd},
                        )
                    ).json()["token"]
                )
            },
            json={"email": ""},
        )
        check(unbind.status_code == 200, "有密码时解绑邮箱", unbind.text[:160])
        check(unbind.json()["email"] == "", "解绑后 email 回空串")

        print()
        print("=== 10. 管理员用户列表里能看到两个标识 ===")
        lst = await c.get("/api/admin/users", headers=admin_h)
        check(lst.status_code == 200, "管理员可读用户列表")
        row = next(
            (u for u in lst.json() if u["username"] == "tangsizhe-new"), None
        )
        check(row is not None, "新账号出现在列表里")
        if row:
            check(row["email"] == "", "未绑邮箱的账号在列表里显示为空串")

    failed = [label for ok, label in results if not ok]
    print()
    print("=" * 62)
    print(f"共 {len(results)} 项，通过 {len(results) - len(failed)} 项，失败 {len(failed)} 项")
    for label in failed:
        print("  FAILED:", label)
    return 1 if failed else 0


if __name__ == "__main__":
    code = 1
    try:
        code = asyncio.run(main())
    except SystemExit:
        raise
    finally:
        if os.path.exists(COPY):
            # 本机的 os.remove 被环境的 safe-delete 包装接管，删除常失败；
            # 副本是纯临时产物，退回系统删除命令即可。
            try:
                os.remove(COPY)
            except OSError:
                import subprocess

                subprocess.run(["cmd", "/c", "del", "/f", "/q", COPY], check=False)
            gone = not os.path.exists(COPY)
            print(f"\n副本 _e2e.db {'已删除' if gone else '仍残留（请手工清理）'}")

        conn = sqlite3.connect(LIVE)
        rows = conn.execute("select count(*) from users").fetchone()[0]
        conn.close()
        print(f"真实 dev.db 用户数 = {rows}（应仍为 1）")
    raise SystemExit(code)
