"""email becomes the login identity

配合「邮箱即账号」，users 表三处调整：
1. username 50 → 100：邮箱最长 100 字符，必须放得下；
2. email 可空 → 必填 + 唯一索引：保证通知一定有收件人，且验证码登录能唯一定位账号；
3. password_hash 必填 → 可空：验证码登录自动创建的账号本来就没有密码
   （这一条是**功能必需**，否则那类账号会直接撞 NOT NULL 插不进去）。

升级前会把历史「空邮箱」的账号补成 `<username>@placeholder.invalid` 占位，
否则对存量数据加 NOT NULL 会直接失败。`.invalid` 是 RFC 2606 保留后缀，
永不解析、不可能误投到真实地址；这类账号需管理员后台改成真邮箱后才能用验证码登录。

Revision ID: 20260920_1300_email_as_identity
Revises: 20260920_0900_guard_workflow_fixes
Create Date: 2026-09-20 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_1300_email_as_identity"
down_revision: str | None = "20260920_0900_guard_workflow_fixes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# RFC 2606 保留后缀：永远解析不到真实主机，用作占位最安全
_PLACEHOLDER_SUFFIX = "@placeholder.invalid"


def _fill_missing_emails() -> None:
    """给历史空邮箱的账号补占位邮箱，让随后的 NOT NULL 约束能加上。"""
    users = sa.table(
        "users",
        sa.column("id", sa.BigInteger()),
        sa.column("username", sa.String(100)),
        sa.column("email", sa.String(100)),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(users.c.id, users.c.username).where(
            sa.or_(users.c.email.is_(None), users.c.email == "")
        )
    ).fetchall()
    for row in rows:
        bind.execute(
            sa.update(users)
            .where(users.c.id == row.id)
            .values(email=f"{row.username}{_PLACEHOLDER_SUFFIX}")
        )


def upgrade() -> None:
    _fill_missing_emails()

    # SQLite 不支持直接改列约束，用 batch 模式重建表（MySQL 下会退化成普通 ALTER）
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "username",
            existing_type=sa.String(50),
            type_=sa.String(100),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "email",
            existing_type=sa.String(100),
            nullable=False,
        )
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(255),
            nullable=True,
        )

    inspector = sa.inspect(op.get_bind())
    has_unique_email = any(
        index.get("unique") and tuple(index["column_names"]) == ("email",)
        for index in inspector.get_indexes("users")
    )
    if not has_unique_email:
        op.create_index("uq_users_email", "users", ["email"], unique=True)


def _fill_missing_password_hashes() -> None:
    """回退前给「没有密码」的账号补一个随机哈希。

    补的是**真实可校验的 bcrypt 哈希**，但原密码是当场生成的随机串、谁也不知道，
    效果等同于「该账号只能用验证码登录」，只是满足了 NOT NULL 约束。
    不补的话，回退时遇到这类账号会直接失败。
    """
    import secrets

    from passlib.context import CryptContext

    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    users = sa.table(
        "users",
        sa.column("id", sa.BigInteger()),
        sa.column("password_hash", sa.String(255)),
    )
    bind = op.get_bind()
    ids = bind.execute(
        sa.select(users.c.id).where(users.c.password_hash.is_(None))
    ).scalars().all()
    for user_id in ids:
        bind.execute(
            sa.update(users)
            .where(users.c.id == user_id)
            .values(password_hash=ctx.hash(secrets.token_urlsafe(32)))
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if any(
        index.get("unique") and tuple(index["column_names"]) == ("email",)
        for index in inspector.get_indexes("users")
    ):
        op.drop_index("uq_users_email", table_name="users")

    _fill_missing_password_hashes()

    with op.batch_alter_table("users") as batch_op:
        # 回退到「必须有密码」：无密码账号已在上面补过随机哈希
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(255),
            nullable=False,
            existing_server_default=None,
        )
        batch_op.alter_column(
            "email",
            existing_type=sa.String(100),
            nullable=True,
        )
        batch_op.alter_column(
            "username",
            existing_type=sa.String(100),
            type_=sa.String(50),
            existing_nullable=False,
        )
