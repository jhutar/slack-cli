import argparse
import sys

from slack_cli import __version__
from slack_cli.commands import login, read
from slack_cli.config import load_config
from slack_cli.log import setup_logging


def main():
    parser = argparse.ArgumentParser(
        prog="slack-cli",
        description="CLI tool to translate Slack links to readable message content",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        "-c",
        metavar="PATH",
        default=None,
        help="path to config file (default: ~/.config/slack-cli/config.toml)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="logging level for stderr output (default: WARNING)",
    )

    subparsers = parser.add_subparsers(dest="subcommand")

    read_parser = subparsers.add_parser(
        "read", help="fetch and display Slack messages from a link"
    )
    read_parser.add_argument("slack_link", metavar="slack-link", help="Slack message URL")
    read_parser.add_argument(
        "--after",
        "-a",
        default=None,
        help="number of follow-up messages (integer) or duration (e.g., 30M, 2H)",
    )

    login_parser = subparsers.add_parser(
        "login", help="fetch xoxc token and write config (experimental)"
    )
    login_parser.add_argument(
        "workspace_url", metavar="workspace-url",
        help="Slack workspace URL (e.g., mywork.slack.com)",
    )
    login_parser.add_argument(
        "--xoxd-token", default=None,
        help="xoxd cookie value; if omitted, reads from config/env or prompts",
    )
    login_parser.add_argument(
        "--user-agent", default=None,
        help="User-Agent header (for enterprise Slack)",
    )

    args = parser.parse_args()

    if args.subcommand is None:
        parser.print_help()
        sys.exit(1)

    config = load_config(args.config)

    if args.log_level:
        config["log_level"] = args.log_level

    setup_logging(
        level=config.get("log_level", "WARNING"),
        log_file=config.get("log_file") or None,
    )

    if args.subcommand == "login":
        login.run(args, config)
    elif args.subcommand == "read":
        read.run(args, config)
