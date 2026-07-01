import os

from mahjong_agent.trial_app_config import (
    build_redis_cache_from_env,
    load_local_env,
    redact_redis_url,
    trial_cache_prefix_from_env,
)


def test_redact_redis_url_keeps_url_without_password() -> None:
    assert redact_redis_url("redis://127.0.0.1:6379/0") == "redis://127.0.0.1:6379/0"


def test_redact_redis_url_masks_password() -> None:
    assert (
        redact_redis_url("redis://user:secret@redis.example.com:6380/2")
        == "redis://user:***@redis.example.com:6380/2"
    )
    assert redact_redis_url("redis://:secret@redis.example.com/0") == "redis://***@redis.example.com/0"


def test_load_local_env_sets_missing_keys_without_overwriting(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "MAHJONG_TEST_EXISTING=from_file",
                "MAHJONG_TEST_NEW='new value'",
                "BAD_LINE_WITHOUT_EQUALS",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MAHJONG_TEST_EXISTING", "from_env")
    monkeypatch.delenv("MAHJONG_TEST_NEW", raising=False)

    load_local_env(env_file)

    assert trial_cache_prefix_from_env("mahjong:trial")
    assert os.environ["MAHJONG_TEST_EXISTING"] == "from_env"
    assert os.environ["MAHJONG_TEST_NEW"] == "new value"


def test_trial_cache_prefix_from_env_strips_edge_colons(monkeypatch) -> None:
    monkeypatch.setenv("MAHJONG_CACHE_PREFIX", ":boss:trial:")

    assert trial_cache_prefix_from_env() == "boss:trial"


def test_build_redis_cache_from_env_disabled(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setenv("MAHJONG_REDIS_URL", "disabled")

    cache = build_redis_cache_from_env(printer=messages.append)

    assert cache is None
    assert messages == ["Redis cache disabled by MAHJONG_REDIS_URL."]
