"""竞品图标库：图标文件托管在后端磁盘上，数据库只记元信息。

为什么需要它：
竞品图标此前只是一条指向外部站点的 URL（competitors.logo_url），图片本体
不在后端——外部站点一改版/封锁（如 Canva 全站 403、docs.qq 的 favicon 返回
HTML）图标就失效，前端只能回退首字母头像。

图标库按**规范化域名**（小写、去 www）做唯一 key：管理员上传一次后，
该域名下的所有竞品（含其他用户添加的）都改用后端托管的图标，
从此与外部站点是否变动解耦。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntPK


class IconLibrary(Base):
    """图标库条目：domain + 磁盘文件名，域名级唯一。"""

    __tablename__ = "icon_libraries"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)

    # 规范化主机名（小写、去 www），作为域名级的唯一 key（口径见 services/icon_library）
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # 磁盘文件名（uuid + 扩展名），位于 settings.storage_dir/icons 下，
    # 对外地址统一是 /api/icons/{file_name}（由 main.py 挂载的静态路由托管）
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)

    # 上传者（管理员）：不加外键，避免删除用户时被图标记录卡住；种子数据为 NULL
    uploaded_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )