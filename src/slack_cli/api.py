import logging
import time
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://slack.com/api"
MAX_RETRIES = 3


class SlackAPIError(Exception):
    def __init__(self, method, error):
        self.method = method
        self.error = error
        super().__init__(f"Slack API error on {method}: {error}")


def _retry_after(e):
    """Seconds from the Retry-After header on a failed response, or None."""
    response = getattr(e, "response", None)
    if response is None:
        return None
    value = response.headers.get("Retry-After", "").strip()
    if not value.isdigit():
        return None
    return int(value)


class SlackAPI:
    def __init__(self, xoxc_token, xoxd_token, user_agent=None):
        self.xoxc_token = xoxc_token
        self.xoxd_token = xoxd_token
        self.user_agent = user_agent

    def call(self, method, params=None):
        """Call a Slack Web API method on slack.com/api/<method>."""
        return self._post(f"{BASE_URL}/{method}", params)

    def call_workspace(self, host, path, params=None):
        """Call a workspace-scoped legacy endpoint (e.g. activity.feed)."""
        return self._post(f"https://{host}/api/{path}", params)

    def _post(self, url, params):
        xoxd_encoded = quote(self.xoxd_token, safe="")
        headers = {"Cookie": f"d={xoxd_encoded}"}
        if self.user_agent:
            headers["User-Agent"] = self.user_agent

        form_data = dict(params or {})
        form_data["token"] = self.xoxc_token

        logger.debug("API call: %s params=%s", url, params)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(url, headers=headers, data=form_data, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                if attempt == MAX_RETRIES:
                    raise SystemExit(f"Error: HTTP request failed for {url}: {e}")
                retry_after = _retry_after(e)
                delay = retry_after if retry_after is not None else attempt
                logger.warning(
                    "HTTP error on %s (attempt %d): %s, retrying in %ds",
                    url,
                    attempt,
                    e,
                    delay,
                )
                time.sleep(delay)
                continue

            data = resp.json()
            logger.debug("API response: %s ok=%s - %s", url, data.get("ok"), data)

            if data.get("ok"):
                return data

            error = data.get("error", "unknown_error")

            if error == "ratelimited":
                retry_after = int(resp.headers.get("Retry-After", attempt))
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Rate limited on %s, retrying in %ds", url, retry_after
                    )
                    time.sleep(retry_after)
                    continue

            raise SlackAPIError(url, error)

        raise SlackAPIError(url, "max_retries_exceeded")

    def call_paginated(self, method, params, key):
        all_items = []
        params = dict(params) if params else {}
        while True:
            resp = self.call(method, params)
            items = resp.get(key, [])
            all_items.extend(items)

            cursor = resp.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
            params["cursor"] = cursor

        return all_items
