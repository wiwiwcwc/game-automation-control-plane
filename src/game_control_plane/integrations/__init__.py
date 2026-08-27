from .base import Integration, LaunchSpec, ValidationResult
from .custom_cli import CustomCliIntegration
from .maa_cli import MaaCliIntegration, discover_maa_cli
from .maa_punish import MaaPunishIntegration, discover_fos
from .ok_ww import OkWwIntegration, discover_ok_ww
from .registry import IntegrationRegistry, default_registry, integration_label

__all__ = [
    "CustomCliIntegration",
    "Integration",
    "IntegrationRegistry",
    "LaunchSpec",
    "MaaCliIntegration",
    "MaaPunishIntegration",
    "OkWwIntegration",
    "ValidationResult",
    "default_registry",
    "discover_maa_cli",
    "discover_fos",
    "discover_ok_ww",
    "integration_label",
]
