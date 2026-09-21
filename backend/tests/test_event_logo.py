"""情报事件接口的图标字段。

顺带覆盖 `_base_select()` 的列顺序：抓取时落库的 logo_url 是后加的一列，
如果查询里加了列而取行处没同步解包，这里会直接炸出来（列表/详情/相关事件共用它）。
"""
from app.core.event_types import EventType
from app.core.security import create_access_token
from app.models.competitor import Competitor
from app.models.event import IntelligenceEvent
from app.models.user import User

STORED_LOGO = "https://cdn.example.com/icon.png"


async def _seed(session: object, *, logo_url: str) -> tuple[User, IntelligenceEvent]:
    u = User(username="alice", email="alice@test.local", password_hash="hashed")
    session.add(u)
    await session.commit()
    await session.refresh(u)

    c = Competitor(
        user_id=u.id,
        name="豆包",
        official_url="https://www.doubao.com",
        logo_url=logo_url,
    )
    session.add(c)
    await session.commit()
    await session.refresh(c)

    e = IntelligenceEvent(
        competitor_id=c.id,
        event_type=list(EventType)[0],
        title="价格变动",
        priority="high",
    )
    session.add(e)
    await session.commit()
    await session.refresh(e)
    return u, e


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def test_event_list_uses_stored_logo(client: object, session: object) -> None:
    u, _ = await _seed(session, logo_url=STORED_LOGO)

    r = await client.get("/api/events", headers=_auth(u))
    assert r.status_code == 200, r.text
    record = r.json()["records"][0]
    assert record["logoUrl"] == STORED_LOGO
    # 内部输入字段不对外多暴露一份
    assert "competitorLogoUrl" not in record


async def test_event_list_falls_back_to_favicon(client: object, session: object) -> None:
    """老数据（还没抓到首页）落库是空串 → 回退官网 favicon。"""
    u, _ = await _seed(session, logo_url="")

    r = await client.get("/api/events", headers=_auth(u))
    assert r.json()["records"][0]["logoUrl"] == "https://doubao.com/favicon.ico"


async def test_event_detail_uses_stored_logo(client: object, session: object) -> None:
    u, event = await _seed(session, logo_url=STORED_LOGO)

    r = await client.get(f"/api/events/{event.id}", headers=_auth(u))
    assert r.status_code == 200, r.text
    assert r.json()["logoUrl"] == STORED_LOGO


async def test_related_events_use_stored_logo(client: object, session: object) -> None:
    u, event = await _seed(session, logo_url=STORED_LOGO)

    r = await client.get(
        "/api/events/related",
        headers=_auth(u),
        params={"competitorId": event.competitor_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()[0]["logoUrl"] == STORED_LOGO
