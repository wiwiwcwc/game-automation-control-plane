from __future__ import annotations

from .base import Integration
from .custom_cli import CustomCliIntegration
from .maa_cli import MaaCliIntegration
from .maa_punish import MaaPunishIntegration
from .onedragon import ZzzOneDragonIntegration
from .ok_ww import OkWwIntegration


INTEGRATION_LABELS = {
    "custom_cli": "Custom CLI",
    "maa_cli": "MAA",
    "maa_punish": "MAA_Punish",
    "ok_ww": "OK-WW",
    "zzz_onedragon": "绝区零 OneDragon",
}


class IntegrationRegistry:
    def __init__(self, integrations: list[Integration] | None = None):
        values = (
            [
                CustomCliIntegration(),
                MaaCliIntegration(),
                MaaPunishIntegration(),
                OkWwIntegration(),
                ZzzOneDragonIntegration(),
            ]
            if integrations is None
            else integrations
        )
        self._integrations = {integration.runner_type: integration for integration in values}

    def get(self, runner_type: str) -> Integration:
        try:
            return self._integrations[runner_type]
        except KeyError as exc:
            raise ValueError(f"Unknown integration type: {runner_type}") from exc

    def types(self) -> tuple[str, ...]:
        return tuple(self._integrations)


def default_registry() -> IntegrationRegistry:
    return IntegrationRegistry()


def integration_label(runner_type: str) -> str:
    return INTEGRATION_LABELS.get(runner_type, runner_type)
