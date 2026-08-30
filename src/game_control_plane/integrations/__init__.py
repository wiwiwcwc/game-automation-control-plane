from .base import Integration, LaunchSpec, ValidationIssue, ValidationResult
from .custom_cli import CustomCliIntegration
from .maa_cli import MaaCliIntegration, discover_maa_cli
from .maa_punish import MaaPunishIntegration, discover_fos
from .onedragon import (
    ZZZ_ONEDRAGON_CLASSIC_NAME,
    ZZZ_ONEDRAGON_CONFIG_VERSION,
    ZZZ_ONEDRAGON_EXECUTABLE_ENV,
    ZZZ_ONEDRAGON_EXECUTABLE_NAMES,
    ZZZ_ONEDRAGON_RUNTIME_NAME,
    ZZZ_ONEDRAGON_RUNNER_TYPE,
    OneDragonIntegration,
    ZzzOneDragonIntegration,
    discover_zzz_onedragon,
    find_child_casefold,
    format_instance_indices,
    launcher_kind,
    parse_instance_indices,
)
from .ok_ww import OkWwIntegration, discover_ok_ww
from .registry import IntegrationRegistry, default_registry, integration_label

__all__ = [
    "CustomCliIntegration",
    "Integration",
    "IntegrationRegistry",
    "LaunchSpec",
    "MaaCliIntegration",
    "MaaPunishIntegration",
    "ZzzOneDragonIntegration",
    "OneDragonIntegration",
    "OkWwIntegration",
    "ValidationResult",
    "ValidationIssue",
    "default_registry",
    "discover_maa_cli",
    "discover_fos",
    "discover_zzz_onedragon",
    "discover_ok_ww",
    "ZZZ_ONEDRAGON_CLASSIC_NAME",
    "ZZZ_ONEDRAGON_CONFIG_VERSION",
    "ZZZ_ONEDRAGON_EXECUTABLE_ENV",
    "ZZZ_ONEDRAGON_EXECUTABLE_NAMES",
    "ZZZ_ONEDRAGON_RUNTIME_NAME",
    "ZZZ_ONEDRAGON_RUNNER_TYPE",
    "find_child_casefold",
    "format_instance_indices",
    "integration_label",
    "launcher_kind",
    "parse_instance_indices",
]
