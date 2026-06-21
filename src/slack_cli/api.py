import logging
import time

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://slack.com/api"
MAX_RETRIES = 3


class SlackAPIError(Exception):
    def __init__(self, method, error):
        self.method = method
        self.error = error
        super().__init__(f"Slack API error on {method}: {error}")


class SlackAPI:
    def __init__(self, xoxc_token, xoxd_token, user_agent=None):
        self.xoxc_token = xoxc_token
        self.xoxd_token = xoxd_token
        self.user_agent = user_agent

    def call(self, method, params=None):
        url = f"{BASE_URL}/{method}"
        headers = {"Authorization": f"Bearer {self.xoxc_token}"}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        cookies = {"d": self.xoxd_token}

        logger.debug("API call: %s params=%s", method, params)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    url, headers=headers, cookies=cookies, data=params or {}
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                if attempt == MAX_RETRIES:
                    raise SystemExit(f"Error: HTTP request failed for {method}: {e}")
                logger.warning("HTTP error on %s (attempt %d): %s", method, attempt, e)
                time.sleep(attempt)
                continue

            data = resp.json()
            logger.debug("API response: %s ok=%s", method, data.get("ok"))

            if data.get("ok"):
                return data

            error = data.get("error", "unknown_error")

            if error == "ratelimited":
                retry_after = int(resp.headers.get("Retry-After", attempt))
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Rate limited on %s, retrying in %ds", method, retry_after
                    )
                    time.sleep(retry_after)
                    continue

            raise SlackAPIError(method, error)

        raise SlackAPIError(method, "max_retries_exceeded")
