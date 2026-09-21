"""split account and email

把「邮箱即账号」拆成两个独立标识：

1. `email` 由「必填 + 唯一」改回「**可空** + 唯一」。账号名（username）重新成为
   独立的自定义登录标识，邮箱退化为**选填**的第二标识（同时也是通知收件人）。
2. 顺带把历史遗留的**空串邮箱**改写成 NULL——空串在唯一索引下只允许存在一条，
   第二个「不填邮箱」的用户会直接 IntegrityError 撞在 `uq_users_email` 上。

`uq_users_email` 唯一索引**保留**：SQLite 与 PostgreSQL 的唯一索引都允许多个 NULL，
所以「唯一」与「可空」并不矛盾，多个不填邮箱的账号可以共存。

回退（downgrade）时 `email` 要重新变成 NOT NULL，因此必须先把 NULL 补成占位邮箱。
这里用 `u{id}@placeholder.invalid`（按主键构造，天然唯一），**不用** 上一版迁移的
`<username>@placeholder.invalid`——因为账号名现在可能是自定义值、甚至本身含 `@`
（自动建号的账号 username 就是邮箱），拼出来会出现两个 `@`，既难看又可能撞车。
`.invalid` 是 RFC 2606 保留后缀，永不解析、不可能误投真实地址。

链条位置：接在 `20260920_1500_add_competitor_logo`（竞品 Logo 字段）之后。
两条迁移原本都从 `20260920_1300_email_as_identity` 分叉，会造成 alembic
Multiple heads、`upgrade head` 直接跑不了，所以这里串成一条直线。

Revision ID: 20260920_1600_split_account_email
Revises: 20260920_1500_add_competitor_logo
Create Date: 2026-09-20 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_1600_split_account_email"
down_revision: str | None = "20260920_1500_add_competitor_logo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLACEHOLDER_PREFIX = "placeholder.invalid"


def _users_table() -> sa.TableClause:
    return sa.table(
        "users",
        sa.column("id", sa.BigInteger()),
        sa.column("username", sa.String(100)),
        sa.column("email", sa.String(100)),
    )


def _email_is_nullable() -> bool:
    """读当前 email 列的可空性（幂等判断，重复跑迁移也不会炸）。"""
    columns = sa.inspect(op.get_bind()).get_columns("users")
    for column in columns:
        if column["name"] == "email":
            return bool(column.get("nullable", True))
    return True


def _has_unique_email_index() -> bool:
    return any(
        index.get("unique") and tuple(index["column_names"]) == ("email",)
        for index in sa.inspect(op.get_bind()).get_indexes("users")
    )


def _blank_emails_to_null() -> None:
    """空串 → NULL：空串会占用唯一索引中的一个名额，必须清掉。"""
    users = _users_table()
    op.get_bind().execute(
        sa.update(users).where(users.c.email == "").values(email=None)
    )


def _null_emails_to_placeholder() -> None:
    """回退前给 NULL 邮箱补占位值，否则加不上 NOT NULL。"""
    users = _users_table()
    bind = op.get_bind()
    ids = bind.execute(
        sa.select(users.c.id).where(users.c.email.is_(None))
    ).scalars().all()
    for user_id in ids:
        bind.execute(
            sa.update(users)
            .where(users.c.id == user_id)
            .values(email=f"u{user_id}@{_PLACEHOLDER_PREFIX}")
        )


def upgrade() -> None:
    _blank_emails_to_null()

    # SQLite 不支持直接改列约束，用 batch 模式重建表（MySQL 下会退化成普通 ALTER）
    if not _email_is_nullable():
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "email",
                existing_type=sa.String(100),
                nullable=True,
            )

    # 唯一索引保留（允许多个 NULL），只在缺失时补建
    if not _has_unique_email_index():
        op.create_index("uq_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    _null_emails_to_placeholder()

    if _email_is_nullable():
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "email",
                existing_type=sa.String(100),
                nullable=False,
            )
