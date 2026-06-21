import logging
import sys
from pathlib import Path

DEFAULT_LOG_DIR = Path("~/.cache/slack-cli").expanduser()
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "debug.log"


def setup_logging(level="WARNING", log_file=None):
    log_path = Path(log_file) if log_file else DEFAULT_LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("slack_cli")
    root.setLevel(logging.DEBUG)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(getattr(logging, level.upper(), logging.WARNING))
    stderr_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    root.addHandler(stderr_handler)
    root.addHandler(file_handler)

    return root
