import os

import pytest

from slack_cli.config import load_config


def test_load_from_toml(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[auth]\nxoxc_token = "xoxc-test"\nxoxd_token = "xoxd-test"\n'
    )
    config = load_config(str(cfg_file))
    assert config["xoxc_token"] == "xoxc-test"
    assert config["xoxd_token"] == "xoxd-test"


def test_env_var_override(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[auth]\nxoxc_token = "from-file"\n')
    monkeypatch.setenv("SLACK_CLI_XOXC_TOKEN", "from-env")
    config = load_config(str(cfg_file))
    assert config["xoxc_token"] == "from-env"


def test_missing_file_uses_defaults():
    config = load_config("/nonexistent/path/config.toml")
    assert config["xoxc_token"] is None
    assert config["log_level"] == "WARNING"
    assert config["cache_ttl"] == 86400


def test_malformed_toml(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("this is not valid toml [[[")
    with pytest.raises(SystemExit, match="Malformed config"):
        load_config(str(cfg_file))


def test_missing_tokens_are_none():
    config = load_config("/nonexistent/path/config.toml")
    assert config["xoxc_token"] is None
    assert config["xoxd_token"] is None
