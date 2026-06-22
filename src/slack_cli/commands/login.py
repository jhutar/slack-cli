import getpass
import logging
import re
import sys
from urllib.parse import quote

import requests

from slack_cli.api import SlackAPI
from slack_cli.config import DEFAULT_CONFIG_PATH, write_config

logger = logging.getLogger(__name__)


def run(args, config):
    workspace = args.workspace_url.removeprefix("https://").removesuffix("/")
    if not workspace.endswith(".slack.com"):
        workspace = f"{workspace}.slack.com"

    xoxd = args.xoxd_token or config.get("xoxd_token")
    if not xoxd:
        xoxd = getpass.getpass("Enter your xoxd token (from browser Cookie 'd'): ")
    if not xoxd:
        print("Error: No xoxd token provided.", file=sys.stderr)
        sys.exit(2)

    user_agent = args.user_agent or config.get("user_agent") or ""

    print(f"Fetching xoxc token from {workspace}...")
    xoxc = _fetch_xoxc(workspace, xoxd, user_agent)

    print("Verifying authentication...")
    api = SlackAPI(xoxc, xoxd, user_agent=user_agent or None)
    try:
        result = api.call("auth.test")
    except Exception as e:
        print(f"Error: Authentication failed: {e}", file=sys.stderr)
        sys.exit(2)

    team = result.get("team", "unknown")
    user = result.get("user", "unknown")

    config_path = args.config or str(DEFAULT_CONFIG_PATH)
    updates = {"xoxc_token": xoxc, "xoxd_token": xoxd}
    if user_agent:
        updates["user_agent"] = user_agent
    write_config(config_path, updates)

    print(f"Logged in as @{user} in {team}.")
    print(f"Config written to {config_path}")


# https://www.papermtn.co.uk/retrieving-and-using-slack-cookies-for-authentication/
def _fetch_xoxc(workspace, xoxd, user_agent):
    xoxd_encoded = quote(xoxd, safe="")
    headers = {"Cookie": f"d={xoxd_encoded}"}
    if user_agent:
        headers["User-Agent"] = user_agent

    try:
        resp = requests.get(
            f"https://{workspace}/ssb/redirect",
            headers=headers,
            allow_redirects=True,
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Error: Failed to fetch from {workspace}: {e}", file=sys.stderr)
        sys.exit(1)

    tokens = re.findall(r"xoxc-[a-zA-Z0-9-]+", resp.text)
    if not tokens:
        print(
            "Error: Could not find xoxc token in response. "
            "The xoxd cookie may be expired.",
            file=sys.stderr,
        )
        sys.exit(2)

    return tokens[0]
