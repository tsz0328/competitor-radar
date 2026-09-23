import asyncio
import sys

sys.path.insert(0, r"D:\project\competitor-radar\backend")

from app.core.database import SessionLocal  # noqa: E402
from app.services import icon_library  # noqa: E402


async def main() -> None:
    async with SessionLocal() as db:
        before = await _snapshot(db)
        changed = await icon_library.backfill_all_icons(db)
        await db.commit()
        after = await _snapshot(db)
    print("CHANGED=", changed)
    for cid in (2, 20):  # 两个用户各自的 Figma
        print(f"competitor {cid}: {before.get(cid)} -> {after.get(cid)}")


async def _snapshot(db) -> dict:
    from sqlalchemy import select  # noqa: E402
    from app.models.competitor import Competitor  # noqa: E402

    rows = (
        await db.execute(select(Competitor.id, Competitor.name, Competitor.official_url, Competitor.logo_url))
    ).all()
    return {r.id: {"name": r.name, "url": r.official_url, "logo": r.logo_url} for r in rows}


if __name__ == "__main__":
    asyncio.run(main())
