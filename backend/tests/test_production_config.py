"""APP_ENV=production 启动安全配置回归测试。"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

GOOD_SECRET = "0123456789abcdef0123456789abcdef"
GOOD_DB_URL = (
    "mysql+aiomysql://acr:correct-horse-battery-staple"
    "@db.internal:3306/competitor_radar?charset=utf8mb4"
)


def _production_settings(**overrides) -> Settings:
    fields = {
        "app_env": "production",
        "db_url": GOOD_DB_URL,
        "db_auto_create": False,
        "cache_backend": "redis",
        "jwt_secret": GOOD_SECRET,
        "notify_enabled": False,
        "notify_backend": "log",
    }
    fields.update(overrides)
    return Settings(_env_file=None, **fields)


def test_valid_production_settings_pass() -> None:
    settings = _production_settings()
    assert settings.app_env == "production"
    assert settings.db_auto_create is False
    assert settings.cache_backend == "redis"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"jwt_secret": "too-short"}, "jwt_secret 长度"),
        ({"jwt_secret": "change-me-in-production-0123456789"}, "占位"),
        ({"db_auto_create": True}, "db_auto_create 必须是 false"),
        ({"cache_backend": "memory"}, "cache_backend 必须是 redis"),
        (
            {"notify_enabled": True, "notify_backend": "log"},
            "notify_backend 必须是 smtp",
        ),
        (
            {"db_url": "sqlite+aiosqlite:///./dev.db"},
            "服务端数据库",
        ),
        (
            {"db_url": "mysql+aiomysql://u:strong-password@localhost:3306/radar"},
            "localhost 或回环地址",
        ),
        (
            {
                "db_url": (
                    "mysql+aiomysql://acr:acr_change_me@db.internal:3306/"
                    "competitor_radar"
                )
            },
            "示例占位凭据",
        ),
    ],
)
def test_invalid_production_settings_are_rejected(overrides, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _production_settings(**overrides)


def test_development_defaults_do_not_trigger_production_rules() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.db_url.startswith("sqlite")
    assert settings.jwt_secret == "dev-secret-change-me"
