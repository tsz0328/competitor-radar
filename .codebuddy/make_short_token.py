"""签一个 3 分钟后过期的短命 token,用于模拟「即将过期」场景。只做签发,不写库。"""

import sys

sys.path.insert(0, r"D:\project\competitor-radar\backend")

from app.core.security import create_access_token  # noqa: E402

print(create_access_token(1, 3))
