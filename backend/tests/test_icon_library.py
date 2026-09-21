"""竞品图标库：域名规范化、上传校验、同域名批量更新、解析优先级与权限。"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update

from app.core.exceptions import ERR_INVALID_ICON as _ERR_ICON
from app.core.security import create_access_token
from app.models.competitor import Competitor
from app.models.icon_library import IconLibrary
from app.models.user import User
from app.services import icon_library

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _seed_user(session, username: str, *, is_admin: bool = False) -> User:
    u = User(
        username=username,
        email=f"{username}@test.local",
        password_hash="hashed",
        is_admin=is_admin,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def _seed_competitor(
    session, user_id: int, *, name: str, official_url: str, logo_url: str = ""
) -> Competitor:
    c = Competitor(
        user_id=user_id, name=name, official_url=official_url, logo_url=logo_url
    )
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return c


# ==================== normalize_host 口径 ====================


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.Feishu.cn/pricing", "feishu.cn"),
        ("feishu.cn", "feishu.cn"),
        ("HTTPS://WWW.DingTalk.com", "dingtalk.com"),
        ("https://example.com/path?x=1#y", "example.com"),
        ("docs.qq.com/doc/xxx", "docs.qq.com"),
        ("", ""),
        (None, ""),
        ("   ", ""),
    ],
)
def test_normalize_host(raw, expected):
    assert icon_library.normalize_host(raw) == expected


# ==================== 图标库命中即应用 ====================


async def test_apply_icon_overrides_existing_logo(session) -> None:
    alice = await _seed_user(session, "alice")
    c = await _seed_competitor(
        session,
        alice.id,
        name="飞书",
        official_url="https://www.feishu.cn",
        logo_url="https://cdn.example.com/old.png",
    )
    session.add(
        IconLibrary(domain="feishu.cn", file_name="abc.png", content_type="image/png", size=10)
    )
    await session.commit()

    await icon_library.apply_icon_for_competitor(session, c)
    assert c.logo_url == "/api/icons/abc.png"


async def test_apply_icon_ignores_unknown_domain(session) -> None:
    alice = await _seed_user(session, "alice")
    c = await _seed_competitor(
        session, alice.id, name="钉钉", official_url="https://www.dingtalk.com"
    )
    await icon_library.apply_icon_for_competitor(session, c)
    assert c.logo_url == ""


# ==================== favicon 端点命库优先 ====================


async def test_favicon_endpoint_prefers_library(client, session) -> None:
    alice = await _seed_user(session, "alice")
    session.add(
        IconLibrary(domain="qidian.com", file_name="abc123.png", content_type="image/png", size=10)
    )
    await session.commit()

    r = await client.get(
        "/api/competitors/favicon",
        headers=_auth(alice),
        params={"domain": "WWW.QiDian.com"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["logoUrl"] == "/api/icons/abc123.png"


# ==================== 管理员上传 ====================


async def test_upload_requires_admin(client, session, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    alice = await _seed_user(session, "alice")
    c = await _seed_competitor(session, alice.id, name="飞书", official_url="https://www.feishu.cn")

    r = await client.post(
        f"/api/admin/competitors/{c.id}/icon",
        headers=_auth(alice),
        files={"file": ("icon.png", PNG, "image/png")},
    )
    assert r.status_code == 403


async def test_upload_rejects_svg(client, session, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    admin = await _seed_user(session, "admin1", is_admin=True)
    c = await _seed_competitor(session, admin.id, name="飞书", official_url="https://www.feishu.cn")

    r = await client.post(
        f"/api/admin/competitors/{c.id}/icon",
        headers=_auth(admin),
        files={"file": ("icon.svg", b"<svg></svg>", "image/svg+xml")},
    )
    assert r.status_code == 400
    assert r.json()["code"] == _ERR_ICON


async def test_upload_rejects_oversize(client, session, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    admin = await _seed_user(session, "admin1", is_admin=True)
    c = await _seed_competitor(session, admin.id, name="飞书", official_url="https://www.feishu.cn")

    big = b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024)  # 超 2MB 上限
    r = await client.post(
        f"/api/admin/competitors/{c.id}/icon",
        headers=_auth(admin),
        files={"file": ("big.png", big, "image/png")},
    )
    assert r.status_code == 400
    assert r.json()["code"] == _ERR_ICON


async def test_upload_missing_official_url_rejected(
    client, session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    admin = await _seed_user(session, "admin1", is_admin=True)
    c = await _seed_competitor(session, admin.id, name="无官网", official_url="")

    r = await client.post(
        f"/api/admin/competitors/{c.id}/icon",
        headers=_auth(admin),
        files={"file": ("icon.png", PNG, "image/png")},
    )
    assert r.status_code == 400
    assert r.json()["code"] == _ERR_ICON


async def test_upload_updates_same_domain_competitors(
    client, session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    admin = await _seed_user(session, "admin1", is_admin=True)
    alice = await _seed_user(session, "alice")
    bob = await _seed_user(session, "bob")
    c1 = await _seed_competitor(session, alice.id, name="飞书", official_url="https://www.feishu.cn")
    c2 = await _seed_competitor(session, bob.id, name="飞书国际", official_url="https://feishu.cn/zh")
    other = await _seed_competitor(
        session,
        bob.id,
        name="钉钉",
        official_url="https://www.dingtalk.com",
        logo_url="https://cdn.example.com/old.png",
    )

    r = await client.post(
        f"/api/admin/competitors/{c1.id}/icon",
        headers=_auth(admin),
        files={"file": ("icon.png", PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    url = r.json()["logoUrl"]
    assert url.startswith("/api/icons/")
    assert (tmp_path / url.removeprefix("/api/icons/")).read_bytes() == PNG

    # 同域名竞品（含其他用户的）一并换用后端图标；其他域名不动
    await session.refresh(c2)
    await session.refresh(other)
    assert c2.logo_url == url
    assert other.logo_url == "https://cdn.example.com/old.png"

    # 库里记一条域名级记录
    rows = (await session.execute(select(IconLibrary))).scalars().all()
    assert [(row.domain, row.uploaded_by) for row in rows] == [("feishu.cn", admin.id)]


async def test_reupload_replaces_old_file(client, session, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    admin = await _seed_user(session, "admin1", is_admin=True)
    c = await _seed_competitor(session, admin.id, name="飞书", official_url="https://www.feishu.cn")

    r1 = await client.post(
        f"/api/admin/competitors/{c.id}/icon",
        headers=_auth(admin),
        files={"file": ("a.png", PNG, "image/png")},
    )
    assert r1.status_code == 200, r1.text
    url1 = r1.json()["logoUrl"]

    png2 = PNG + b"second"
    r2 = await client.post(
        f"/api/admin/competitors/{c.id}/icon",
        headers=_auth(admin),
        files={"file": ("b.png", png2, "image/png")},
    )
    assert r2.status_code == 200, r2.text
    url2 = r2.json()["logoUrl"]
    assert url2 != url1

    # 旧文件被清理，库里仍只有一条记录
    assert not (tmp_path / url1.removeprefix("/api/icons/")).exists()
    rows = (await session.execute(select(IconLibrary))).scalars().all()
    assert len(rows) == 1
    assert rows[0].file_name == url2.removeprefix("/api/icons/")


async def test_upload_competitor_not_found(client, session, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    admin = await _seed_user(session, "admin1", is_admin=True)

    r = await client.post(
        "/api/admin/competitors/9999/icon",
        headers=_auth(admin),
        files={"file": ("icon.png", PNG, "image/png")},
    )
    assert r.status_code == 404


# ==================== 管理员全部竞品列表 ====================


async def test_admin_list_all_competitors(client, session) -> None:
    alice = await _seed_user(session, "alice")
    bob = await _seed_user(session, "bob")
    admin = await _seed_user(session, "admin1", is_admin=True)
    await _seed_competitor(session, alice.id, name="飞书", official_url="https://www.feishu.cn")
    await _seed_competitor(session, bob.id, name="钉钉", official_url="https://www.dingtalk.com")

    r = await client.get("/api/admin/competitors", headers=_auth(admin))
    assert r.status_code == 200, r.text
    by_name = {row["name"]: row for row in r.json()}
    assert set(by_name) == {"飞书", "钉钉"}
    assert by_name["飞书"]["ownerUsername"] == "alice"
    assert by_name["钉钉"]["ownerUsername"] == "bob"


async def test_admin_list_competitors_requires_admin(client, session) -> None:
    alice = await _seed_user(session, "alice")
    await _seed_competitor(session, alice.id, name="飞书", official_url="https://www.feishu.cn")

    r = await client.get("/api/admin/competitors", headers=_auth(alice))
    assert r.status_code == 403


async def test_admin_list_competitors_filters_deleted(client, session) -> None:
    alice = await _seed_user(session, "alice")
    admin = await _seed_user(session, "admin1", is_admin=True)
    await _seed_competitor(session, alice.id, name="飞书", official_url="https://www.feishu.cn")
    trashed = await _seed_competitor(session, alice.id, name="钉钉", official_url="https://www.dingtalk.com")

    await session.execute(
        update(Competitor)
        .where(Competitor.id == trashed.id)
        .values(deleted_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
    )
    await session.commit()

    r = await client.get("/api/admin/competitors", headers=_auth(admin))
    assert r.status_code == 200, r.text
    assert [row["name"] for row in r.json()] == ["飞书"]