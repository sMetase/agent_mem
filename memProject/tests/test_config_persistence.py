from pathlib import Path

import pytest

from app.core.config import load_settings, persist_generation_schedule


def test_persist_generation_schedule_preserves_yaml_content(tmp_path: Path):
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        """app:\n  name: \"Agent Memory System\"\n\ngeneration:\n  # Keep this comment.\n  extraction_schedule_enabled: false\n  extraction_window_start: \"00:00\"\n  extraction_window_end: \"23:59\"\n  extraction_timezone: \"Asia/Shanghai\"\n\ndatabase:\n  host: \"${DB_HOST:-localhost}\"\n""",
        encoding="utf-8",
    )

    persist_generation_schedule(
        {
            "extraction_schedule_enabled": True,
            "extraction_window_start": "22:00",
            "extraction_window_end": "06:00",
            "extraction_timezone": "UTC",
        },
        config_path=str(config_path),
    )

    content = config_path.read_text(encoding="utf-8")
    assert "# Keep this comment." in content
    assert 'host: "${DB_HOST:-localhost}"' in content
    assert "extraction_schedule_enabled: true" in content
    assert 'extraction_window_start: "22:00"' in content
    assert 'extraction_window_end: "06:00"' in content
    assert 'extraction_timezone: "UTC"' in content

    settings = load_settings(str(config_path))
    assert settings.generation.extraction_schedule_enabled is True
    assert settings.generation.extraction_window_start == "22:00"
    assert settings.generation.extraction_window_end == "06:00"
    assert settings.generation.extraction_timezone == "UTC"


def test_persist_generation_schedule_rejects_unknown_fields(tmp_path: Path):
    config_path = tmp_path / "settings.yaml"
    config_path.write_text("generation:\n  extraction_schedule_enabled: false\n", encoding="utf-8")

    with pytest.raises(ValueError, match="不允许持久化配置字段"):
        persist_generation_schedule({"debug": True}, config_path=str(config_path))
