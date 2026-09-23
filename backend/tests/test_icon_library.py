"""竞品图标库：域名规范化、上传校验、同域名批量更新、解析优先级与权限。"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update

from app.core.exceptions import ERR_INVALID_ICON as _ERR_ICON
from app.core.security import create_access_token
from app.models.competitor import Competitor
from app.models.icon_library import IconLibrary
from app.models.user import User
from app.services import favicon, icon_library

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


# ==================== 批量查库 / 全量回填 ====================


async def test_icon_url_by_domain_dedup_and_ignores_empty(session) -> None:
    """批量命中图标库：去空去重，库里没有的域名不出现在结果里。"""
    session.add(
        IconLibrary(domain="feishu.cn", file_name="a.png", content_type="image/png", size=10)
    )
    await session.commit()

    out = await icon_library.icon_url_by_domain(
        session, ["https://www.feishu.cn", "feishu.cn", "", "unknown.com", None]
    )
    assert out == {"feishu.cn": "/api/icons/a.png"}


async def test_backfill_resyncs_stale_logo_url(session) -> None:
    """全量回填：把创建早于图标库收录、logo_url 陈旧的竞品重新对齐到库里当前图标。

    这正是「同一站点（如 figma.com / www.figma.com）在不同用户的竞品上显示不同图标」
    的根因修复——两条记录域名归一化后同属一个图标库 key，回填后 logo_url 一致。
    """
    alice = await _seed_user(session, "alice")
    bob = await _seed_user(session, "bob")
    # 两个用户各加一条 figma，官网写法不同（www / 无 www），但归一化后都是 figma.com
    stale_a = await _seed_competitor(
        session, alice.id, name="Figma", official_url="https://www.figma.com", logo_url=""
    )
    stale_b = await _seed_competitor(
        session, bob.id, name="Figma", official_url="https://figma.com", logo_url=""
    )
    # 另一条无关竞品，库里没有它的域名，logo_url 应保持原样
    untouched = await _seed_competitor(
        session, bob.id, name="钉钉", official_url="https://www.dingtalk.com", logo_url=""
    )
    session.add(
        IconLibrary(domain="figma.com", file_name="figma.png", content_type="image/png", size=10)
    )
    await session.commit()

    changed = await icon_library.backfill_all_icons(session)

    await session.refresh(stale_a)
    await session.refresh(stale_b)
    await session.refresh(untouched)
    assert changed == 2
    # 两条 figma 都对齐到同一图标，不再因创建时机/官网写法不同而分叉
    assert stale_a.logo_url == "/api/icons/figma.png"
    assert stale_b.logo_url == "/api/icons/figma.png"
    # 库里没有 dingtalk.com，这条保持原样（空串）
    assert untouched.logo_url == ""


# ==================== 读取时自愈（列表/详情） ====================


async def test_list_returns_library_icon_over_stale_logo(client, session) -> None:
    """列表读取时自愈：记录的 logo_url 为空，但图标库已有该域名图标，应返回库里图标。

    锁死「创建时机早于图标库收录 → 列表仍显示库里当前图标」这条用户可见的修复路径。
    """
    alice = await _seed_user(session, "alice")
    await _seed_competitor(
        session, alice.id, name="Figma", official_url="https://www.figma.com", logo_url=""
    )
    session.add(
        IconLibrary(domain="figma.com", file_name="figma.png", content_type="image/png", size=10)
    )
    await session.commit()

    r = await client.get("/api/competitors", headers=_auth(alice))
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1
    # 即使记录 logo_url 为空，读取时也对齐到图标库当前值，两个用户/写法都不会分叉
    assert items[0]["logoUrl"] == "/api/icons/figma.png"


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
    body = r.json()
    by_name = {row["name"]: row for row in body["items"]}
    assert body["total"] == 2
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
    assert [row["name"] for row in r.json()["items"]] == ["飞书"]


# ==================== 抓取流程自动沉淀共享图标库 ====================


async def test_save_from_url_registers_domain_and_reuses(
    session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    monkeypatch.setattr(
        icon_library, "_download_image", AsyncMock(return_value=("image/png", PNG))
    )

    url = await icon_library.save_from_url(
        session, "https://www.Notion.so", "https://cdn.notion.so/i.png"
    )
    assert url.startswith("/api/icons/")
    assert (tmp_path / url.removeprefix("/api/icons/")).read_bytes() == PNG

    # 库里只有一条域名级记录，uploaded_by 为空（自动沉淀，非管理员）
    rows = (await session.execute(select(IconLibrary))).scalars().all()
    assert [(r.domain, r.uploaded_by) for r in rows] == [("notion.so", None)]

    # 同域名再次调用：复用既有记录，不再新增、不再重复写盘
    url2 = await icon_library.save_from_url(
        session, "notion.so", "https://cdn.notion.so/j.png"
    )
    assert url2 == url
    rows2 = (await session.execute(select(IconLibrary))).scalars().all()
    assert len(rows2) == 1


async def test_save_from_url_rejects_unsupported_format(
    session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    monkeypatch.setattr(
        icon_library,
        "_download_image",
        AsyncMock(return_value=("image/svg+xml", b"<svg/>")),
    )

    assert await icon_library.save_from_url(session, "x.com", "https://x.com/a.svg") is None
    # 不写文件、不写库
    assert list(tmp_path.iterdir()) == []
    assert (await session.execute(select(IconLibrary))).scalars().all() == []


async def test_auto_icon_reused_across_users(session, monkeypatch, tmp_path) -> None:
    """首个用户抓取沉淀的图标库，其他用户添加同域名竞品时直接复用。"""
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    monkeypatch.setattr(
        icon_library, "_download_image", AsyncMock(return_value=("image/png", PNG))
    )
    alice = await _seed_user(session, "alice")
    bob = await _seed_user(session, "bob")
    ca = await _seed_competitor(
        session, alice.id, name="Notion", official_url="https://www.notion.so"
    )
    cb = await _seed_competitor(
        session, bob.id, name="Notion 国际", official_url="https://notion.so/x"
    )

    # alice 的竞品抓取时把图标沉淀进共享库
    await icon_library.save_from_url(session, ca.official_url, "https://cdn.notion.so/i.png")
    # bob 添加同域名竞品：创建时直接命中共享库，无需再抓
    await icon_library.apply_icon_for_competitor(session, ca)
    await icon_library.apply_icon_for_competitor(session, cb)
    assert ca.logo_url == cb.logo_url
    assert ca.logo_url.startswith("/api/icons/")

    rows = (await session.execute(select(IconLibrary))).scalars().all()
    assert len(rows) == 1


# ==================== 管理员重新获取图标 ====================


async def test_refresh_icon_resolves_and_updates_same_domain(
    client, session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    monkeypatch.setattr(
        favicon, "_probe", AsyncMock(return_value="https://cdn.feishu.cn/favicon.png")
    )
    monkeypatch.setattr(
        icon_library, "save_from_url", AsyncMock(return_value="/api/icons/feishu.png")
    )
    admin = await _seed_user(session, "admin1", is_admin=True)
    alice = await _seed_user(session, "alice")
    bob = await _seed_user(session, "bob")
    c1 = await _seed_competitor(session, alice.id, name="飞书", official_url="https://www.feishu.cn")
    c2 = await _seed_competitor(session, bob.id, name="飞书国际", official_url="https://feishu.cn/x")
    other = await _seed_competitor(
        session, bob.id, name="钉钉", official_url="https://www.dingtalk.com"
    )

    r = await client.post(
        f"/api/admin/competitors/{c1.id}/refresh-icon", headers=_auth(admin)
    )
    assert r.status_code == 200, r.text
    assert r.json()["logoUrl"] == "/api/icons/feishu.png"

    # 同域名（含其他用户）竞品一并更新；其他域名不动
    await session.refresh(c2)
    await session.refresh(other)
    assert c2.logo_url == "/api/icons/feishu.png"
    assert other.logo_url == ""


async def test_refresh_icon_cross_domain_returns_error(
    client, session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    # 跨域跳转（被收购/停放）→ _probe 修复后返回 None
    monkeypatch.setattr(favicon, "_probe", AsyncMock(return_value=None))
    admin = await _seed_user(session, "admin1", is_admin=True)
    c = await _seed_competitor(
        session, admin.id, name="某竞品", official_url="https://www.example.com"
    )

    r = await client.post(
        f"/api/admin/competitors/{c.id}/refresh-icon", headers=_auth(admin)
    )
    assert r.status_code == 400
    assert r.json()["code"] == _ERR_ICON


async def test_refresh_icon_requires_admin(client, session, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(icon_library, "icons_dir", lambda: tmp_path)
    alice = await _seed_user(session, "alice")
    c = await _seed_competitor(session, alice.id, name="飞书", official_url="https://www.feishu.cn")

    r = await client.post(
        f"/api/admin/competitors/{c.id}/refresh-icon", headers=_auth(alice)
    )
    assert r.status_code == 403


# ==================== 修改官网地址 → 旧图标失效 ====================


async def test_update_official_url_reuses_new_domain_shared_icon(
    client, session
) -> None:
    """改官网地址后，若新域名已在共享图标库，直接复用，不再显示旧域名图标。

    对应真实场景：智能检测把 Trae 官网错填成 trae.com，用户改正为 trae.cn 后，
    图标应换成 trae.cn 的，而非停留在 trae.com 的图标。
    """
    owner = await _seed_user(session, "owner")
    c = await _seed_competitor(
        session,
        owner.id,
        name="Trae",
        official_url="https://trae.com",
        logo_url="https://trae.com/favicon.ico",  # 旧地址的错误图标
    )
    session.add(
        IconLibrary(
            domain="trae.cn",
            file_name="trae_cn.png",
            content_type="image/png",
            size=len(PNG),
            uploaded_by=None,
        )
    )
    await session.commit()

    r = await client.patch(
        f"/api/competitors/{c.id}",
        json={"officialUrl": "https://trae.cn"},
        headers=_auth(owner),
    )
    assert r.status_code == 200, r.text
    assert r.json()["logoUrl"] == "/api/icons/trae_cn.png"
    assert "trae.com" not in r.json()["logoUrl"]


async def test_update_official_url_clears_stale_logo_when_no_shared_icon(
    client, session
) -> None:
    """改官网地址后，若新域名尚无共享图标，旧域名图标必须清空、不再残留。

    清空后的本行 logo_url 为空，等待下次抓取或管理员「重新获取」补新域名图标；
    analyzer 的 `if competitor.logo_url: return` 守卫因此也会重新解析（旧值不再卡死）。
    """
    owner = await _seed_user(session, "owner")
    c = await _seed_competitor(
        session,
        owner.id,
        name="Trae",
        official_url="https://trae.com",
        logo_url="https://trae.com/favicon.ico",  # 旧地址的错误图标
    )

    r = await client.patch(
        f"/api/competitors/{c.id}",
        json={"officialUrl": "https://trae.cn"},
        headers=_auth(owner),
    )
    assert r.status_code == 200, r.text
    # 旧域名图标彻底消失
    assert "trae.com" not in r.json()["logoUrl"]
    # DB 内本行 logo_url 已清空，等待补新域名图标
    await session.refresh(c)
    assert c.logo_url == ""