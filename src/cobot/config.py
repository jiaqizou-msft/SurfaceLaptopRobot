"""
Configuration loader for MyCobotAgent.
Reads config.yaml and provides typed access to all settings.
"""

import os
import re
import yaml
from dataclasses import dataclass, field
from typing import List, Tuple

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")


def _expand_env_vars(obj):
    """Recursively expand ${ENV_VAR} references in string values."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                obj[k] = re.sub(
                    r"\$\{(\w+)\}",
                    lambda m: os.environ.get(m.group(1), m.group(0)),
                    v,
                )
            else:
                _expand_env_vars(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = re.sub(
                    r"\$\{(\w+)\}",
                    lambda m: os.environ.get(m.group(1), m.group(0)),
                    v,
                )
            else:
                _expand_env_vars(v)


@dataclass
class RobotConfig:
    host: str = "192.168.1.159"
    port: int = 9000
    default_speed: int = 30
    safe_height: int = 230
    default_rx: float = 0
    default_ry: float = 180
    default_rz: float = 90


@dataclass
class CameraConfig:
    stream_url: str = "http://192.168.1.159:8080/video"
    snapshot_url: str = "http://192.168.1.159:8080/snapshot"
    save_dir: str = "temp"


@dataclass
class CalibrationConfig:
    pixel_1: List[float] = field(default_factory=lambda: [130, 290])
    robot_1: List[float] = field(default_factory=lambda: [-21.8, -197.4])
    pixel_2: List[float] = field(default_factory=lambda: [640, 0])
    robot_2: List[float] = field(default_factory=lambda: [215.0, -59.1])


@dataclass
class VLMConfig:
    azure_endpoint: str = ""
    azure_api_key: str = ""
    model: str = "gpt-4o"
    max_tokens: int = 1024


@dataclass
class AppConfig:
    robot: RobotConfig = field(default_factory=RobotConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    vlm: VLMConfig = field(default_factory=VLMConfig)
    top_view_angles: List[float] = field(
        default_factory=lambda: [-62.13, 8.96, -87.71, -14.41, 2.54, -16.34]
    )


def load_config(config_path: str = None) -> AppConfig:
    """Load configuration from YAML file. Supports ${ENV_VAR} expansion."""
    if config_path is None:
        config_path = os.path.abspath(CONFIG_PATH)

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Expand environment variables in string values
    _expand_env_vars(raw)

    cfg = AppConfig()

    if "robot" in raw:
        cfg.robot = RobotConfig(**raw["robot"])
    if "camera" in raw:
        cfg.camera = CameraConfig(**raw["camera"])
    if "calibration" in raw:
        cfg.calibration = CalibrationConfig(**raw["calibration"])
    if "vlm" in raw:
        cfg.vlm = VLMConfig(**raw["vlm"])
    if "top_view_angles" in raw:
        cfg.top_view_angles = raw["top_view_angles"]

    return cfg


# Singleton config instance
_config: AppConfig = None


def get_config() -> AppConfig:
    """Get the global config singleton. Loads from disk on first call."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
