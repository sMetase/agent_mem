from datetime import datetime

import pytest
from pydantic import ValidationError

from app.api.v1.config import ExtractionScheduleRequest
from app.services import l1_worker


def test_extraction_schedule_disabled_is_always_open(monkeypatch):
    monkeypatch.setattr(l1_worker.settings.generation, "extraction_schedule_enabled", False)

    assert l1_worker._is_extraction_window_open(datetime(2026, 9, 6, 2, 0))


def test_extraction_schedule_supports_normal_window(monkeypatch):
    schedule = l1_worker.settings.generation
    monkeypatch.setattr(schedule, "extraction_schedule_enabled", True)
    monkeypatch.setattr(schedule, "extraction_timezone", "Asia/Shanghai")
    monkeypatch.setattr(schedule, "extraction_window_start", "22:00")
    monkeypatch.setattr(schedule, "extraction_window_end", "23:30")

    assert l1_worker._is_extraction_window_open(datetime(2026, 9, 6, 22, 15))
    assert not l1_worker._is_extraction_window_open(datetime(2026, 9, 6, 23, 30))


def test_extraction_schedule_supports_cross_midnight_window(monkeypatch):
    schedule = l1_worker.settings.generation
    monkeypatch.setattr(schedule, "extraction_schedule_enabled", True)
    monkeypatch.setattr(schedule, "extraction_timezone", "Asia/Shanghai")
    monkeypatch.setattr(schedule, "extraction_window_start", "23:00")
    monkeypatch.setattr(schedule, "extraction_window_end", "06:00")

    assert l1_worker._is_extraction_window_open(datetime(2026, 9, 6, 23, 30))
    assert l1_worker._is_extraction_window_open(datetime(2026, 9, 6, 5, 59))
    assert not l1_worker._is_extraction_window_open(datetime(2026, 9, 6, 12, 0))


def test_extraction_schedule_request_validates_time_and_timezone():
    request = ExtractionScheduleRequest(
        extraction_window_start="23:00",
        extraction_window_end="06:00",
        extraction_timezone="Asia/Shanghai",
    )
    assert request.extraction_window_start == "23:00"

    with pytest.raises(ValidationError):
        ExtractionScheduleRequest(extraction_window_start="25:00")
    with pytest.raises(ValidationError):
        ExtractionScheduleRequest(extraction_timezone="Not/A_Timezone")