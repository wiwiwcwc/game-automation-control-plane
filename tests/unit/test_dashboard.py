from __future__ import annotations

import json

from PySide6.QtWidgets import QApplication

from game_control_plane.domain.models import DailyStatus, Job
from game_control_plane.ui.dashboard import JobCard


_APP: QApplication | None = None


def app_instance() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def make_job() -> Job:
    return Job(
        id=1,
        game_id=1,
        game_name="Wuthering Waves",
        name="Daily",
        runner_type="ok_ww",
        runner_config_version=1,
        runner_config_json=json.dumps({"config_version": 1}),
        enabled=True,
        queue_order=1,
        timezone_id="UTC",
        reset_minute=240,
    )


def test_queue_only_locks_cards_that_are_part_of_that_queue():
    app_instance()
    card = JobCard()
    job = make_job()

    card.set_job(job, DailyStatus.PENDING, None, False, None, queue_active=True)
    assert card.run_button.isEnabled()

    card.set_job(job, DailyStatus.PENDING, None, False, "queued", queue_active=True)
    assert not card.run_button.isEnabled()
