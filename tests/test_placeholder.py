def test_import():
    import slack_cli

    assert slack_cli.__version__ == "0.1.0"
