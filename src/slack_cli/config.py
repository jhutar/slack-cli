import os
import tomllib
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("~/.config/slack-cli/config.toml").expanduser()

DEFAULTS = {
    "xoxc_token": None,
    "xoxd_token": None,
    "user_agent": None,
    "log_level": "WARNING",
    "log_file": "",
    "cache_ttl": 86400,
}


def load_config(config_path=None):
    config = dict(DEFAULTS)

    file_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if file_path.exists():
        try:
            with open(file_path, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise SystemExit(f"Error: Malformed config file {file_path}: {e}")

        auth = data.get("auth", {})
        if "xoxc_token" in auth:
            config["xoxc_token"] = auth["xoxc_token"]
        if "xoxd_token" in auth:
            config["xoxd_token"] = auth["xoxd_token"]
        if "user_agent" in auth:
            config["user_agent"] = auth["user_agent"]

        logging_cfg = data.get("logging", {})
        if "level" in logging_cfg:
            config["log_level"] = logging_cfg["level"]
        if "log_file" in logging_cfg:
            config["log_file"] = logging_cfg["log_file"]

        cache_cfg = data.get("cache", {})
        if "ttl" in cache_cfg:
            config["cache_ttl"] = cache_cfg["ttl"]

    env_xoxc = os.environ.get("SLACK_CLI_XOXC_TOKEN")
    if env_xoxc:
        config["xoxc_token"] = env_xoxc

    env_xoxd = os.environ.get("SLACK_CLI_XOXD_TOKEN")
    if env_xoxd:
        config["xoxd_token"] = env_xoxd

    env_ua = os.environ.get("SLACK_CLI_USER_AGENT")
    if env_ua:
        config["user_agent"] = env_ua

    return config
