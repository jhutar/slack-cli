import argparse
import sys

from slack_cli import __version__


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
        default="WARNING",
        help="logging level for stderr output (default: WARNING)",
    )

    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("read", help="fetch and display Slack messages from a link")

    args = parser.parse_args()

    if args.subcommand is None:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
