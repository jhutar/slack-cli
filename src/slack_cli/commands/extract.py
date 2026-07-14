"""Extract subcommand — read tokens from Slack desktop app and write to config."""

import sys

from slack_cli.api import SlackAPI
from slack_cli.config import DEFAULT_CONFIG_PATH, write_config
from slack_cli.slack_tokens import (
    decrypt_cookie,
    extract_tokens,
    find_slack_installation,
)


def run(args, config):
    installation = find_slack_installation()
    print(f"Found Slack installation ({installation['source']}).")

    tokens = extract_tokens(installation["leveldb_path"])

    if args.list:
        _print_workspaces(tokens)
        return

    workspace = _select_workspace(tokens)

    cookie = decrypt_cookie(installation["cookies_path"])

    print("Verifying authentication...")
    api = SlackAPI(workspace["token"], cookie)
    try:
        result = api.call("auth.test")
    except Exception as e:
        print(
            f"Error: Authentication failed: {e}. "
            "The tokens may have expired — try opening Slack to refresh them.",
            file=sys.stderr,
        )
        sys.exit(2)

    team = result.get("team", "unknown")
    user = result.get("user", "unknown")

    config_path = args.config or str(DEFAULT_CONFIG_PATH)
    write_config(config_path, {"xoxc_token": workspace["token"], "xoxd_token": cookie})

    print(f"Logged in as @{user} in {team}.")
    print(f"Config written to {config_path}")


def _print_workspaces(tokens):
    for i, ws in enumerate(tokens, 1):
        print(f"  {i}. {ws['name']} ({ws['url']})")


def _select_workspace(tokens):
    if len(tokens) == 1:
        ws = tokens[0]
        print(f"Extracted 1 workspace: {ws['name']}.")
        return ws

    print(f"Extracted {len(tokens)} workspace(s).")
    _print_workspaces(tokens)

    while True:
        try:
            choice = input("Select workspace [1]: ").strip()
            if not choice:
                return tokens[0]
            idx = int(choice)
            if 1 <= idx <= len(tokens):
                return tokens[idx - 1]
            print(
                f"Please enter a number between 1 and {len(tokens)}.", file=sys.stderr
            )
        except (ValueError, EOFError):
            print(
                f"Please enter a number between 1 and {len(tokens)}.", file=sys.stderr
            )
