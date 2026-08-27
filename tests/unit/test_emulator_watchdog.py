from __future__ import annotations

import json
import sys

from game_control_plane.application.emulator_watchdog import (
    EmulatorWatchdog,
    MuMuWatchSpec,
    interpret_mumu_info,
)


def test_running_mumu_instance_is_ready():
    ready, reason = interpret_mumu_info(
        json.dumps(
            {
                "error_code": 0,
                "is_process_started": True,
                "is_android_started": True,
            }
        ),
        1,
    )

    assert ready is True
    assert reason == ""


def test_closed_mumu_instance_is_lost():
    ready, reason = interpret_mumu_info(
        json.dumps(
            {
                "error_code": 0,
                "is_process_started": False,
                "is_android_started": False,
            }
        ),
        1,
    )

    assert ready is False
    assert "instance 1 was closed" in reason


def test_unreadable_mumu_status_is_unknown_not_immediate_loss():
    ready, reason = interpret_mumu_info("not json", 1)

    assert ready is None
    assert "unreadable" in reason


def test_watchdog_requires_two_confirmed_stopped_responses():
    watchdog = EmulatorWatchdog(
        MuMuWatchSpec(sys.executable, 7),
        lost_confirmation_count=2,
    )
    reasons: list[str] = []
    watchdog.lost.connect(reasons.append)

    watchdog._record_lost("instance stopped")
    assert reasons == []
    watchdog._record_lost("instance stopped")

    assert reasons == ["instance stopped"]
    assert watchdog._probe.arguments() == ["info", "--vmindex", "7"]


def test_probe_command_failures_do_not_stop_a_running_maa_job():
    watchdog = EmulatorWatchdog(MuMuWatchSpec(sys.executable, 1))
    reasons: list[str] = []
    watchdog.lost.connect(reasons.append)

    watchdog._record_probe_failure("temporary error")
    watchdog._record_probe_failure("temporary error")
    watchdog._record_probe_failure("temporary error")

    assert reasons == []
