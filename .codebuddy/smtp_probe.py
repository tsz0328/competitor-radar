"""SMTP 自发自收可行性探测（**不发任何邮件**）。

手法：登录后手工执行 MAIL FROM / RCPT TO / RSET，只读取服务器返回码。
- 250 = 服务器接受该地址
- 553 = Mail from must equal authorized user（发件地址必须与授权账号一致）

不调用 sendmail / send_message，因此客户端不会进入 DATA 阶段，不会投递任何邮件。
凭据全部从 backend/.env 与 dev.db 读取，脚本内不写死、不打印密码。
"""
import os
import sqlite3
import smtplib

BASE = r"D:\project\competitor-radar\backend"


def load_env() -> dict:
    env = {}
    path = os.path.join(BASE, ".env")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            env[k.strip().upper()] = v.strip()
    return env


def admin_email() -> str:
    conn = sqlite3.connect(os.path.join(BASE, "dev.db"))
    try:
        row = conn.execute(
            "select email from users where is_admin = 1 order by id limit 1"
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else ""


def main() -> int:
    env = load_env()
    host = env.get("SMTP_HOST", "")
    port = int(env.get("SMTP_PORT") or 465)
    username = env.get("SMTP_USERNAME", "")
    password = env.get("SMTP_PASSWORD", "")
    sender = env.get("SMTP_SENDER") or username
    recipient = admin_email()

    print("=== 生效配置（授权码只报长度）===")
    print(f"  host      = {host}:{port}")
    print(f"  username  = {username}")
    print(f"  sender    = {sender}")
    print(f"  recipient = {recipient}   (admin 的登录邮箱)")
    print(f"  password  = {'已填(%d字符)' % len(password) if password else '(空)'}")
    print()

    if not (host and username and password and sender and recipient):
        print("配置不完整，无法探测")
        return 1

    with smtplib.SMTP_SSL(host, port, timeout=20) as client:
        code, msg = client.ehlo()
        print(f"connect+ehlo : {code} {msg.decode(errors='replace').strip()}")
        client.login(username, password)
        print("login        : OK  授权码有效")
        print()

        print("=== 探测 1：From = 生效发件邮箱（当前配置）===")
        code, msg = client.docmd("MAIL", f"FROM:<{sender}>")
        print(f"  MAIL FROM:<{sender}>")
        print(f"    -> {code} {msg.decode(errors='replace').strip()}")
        from_ok = code == 250

        if from_ok:
            code, msg = client.docmd("RCPT", f"TO:<{recipient}>")
            print(f"  RCPT TO:<{recipient}>")
            print(f"    -> {code} {msg.decode(errors='replace').strip()}")
            print(f"  自发自收是否被接受：{'是' if code == 250 else '否'}")
            client.docmd("RSET")
        print()

        print("=== 探测 2：From 改成别的地址（演示「发件邮箱必须=授权账号」）===")
        print("  注意：QQ 会直接掐断连接（不是回 553），因此本探测跑完连接即废，")
        print("        每次只应在真有需要时跑一次，避免触发服务端风控。")
        try:
            code, msg = client.docmd("MAIL", "FROM:<noreply@example.com>")
            print("  MAIL FROM:<noreply@example.com>")
            print(f"    -> {code} {msg.decode(errors='replace').strip()}")
        except smtplib.SMTPServerDisconnected:
            print("  MAIL FROM:<noreply@example.com>")
            print("    -> 连接被服务器直接断开（未回 4xx/5xx，比 553 更粗暴）")
            return 0

        client.docmd("RSET")
        client.quit()
    print()
    print("（全程未调用 sendmail/send_message，未产生任何邮件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
