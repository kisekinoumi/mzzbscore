# utils/core/myanimelist_config.py
# MyAnimeList API authentication configuration.

import logging
import os
from typing import Dict, Optional

from utils.network.headers import RequestHeaders


CLIENT_ID_ENV = "MAL_CLIENT_ID"
ACCESS_TOKEN_ENV = "MAL_ACCESS_TOKEN"
DEFAULT_CLIENT_ID = "a382e09bb64ad5e6c8c15fc13057807e"


class MyAnimeListAPIConfig:
    """Loads MyAnimeList API credentials from env vars or the built-in default."""

    def __init__(self):
        self.client_id = ""
        self.access_token = ""
        self.source = ""
        self.reload()

    def reload(self) -> None:
        env_client_id = os.getenv(CLIENT_ID_ENV, "").strip()
        env_access_token = os.getenv(ACCESS_TOKEN_ENV, "").strip()

        self.client_id = env_client_id or DEFAULT_CLIENT_ID
        self.access_token = env_access_token

        if env_client_id or env_access_token:
            self.source = "environment"
        elif self.client_id:
            self.source = "built-in default"
        else:
            self.source = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id or self.access_token)

    def get_headers(self) -> Optional[Dict[str, str]]:
        if not self.is_configured:
            return None

        headers = RequestHeaders.get_custom_headers(accept="application/json")
        headers.pop("Upgrade-Insecure-Requests", None)

        if self.client_id:
            headers["X-MAL-CLIENT-ID"] = self.client_id

        if self.access_token:
            token = self.access_token
            headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"

        return headers

    def set_runtime_client_id(self, client_id: str) -> None:
        self.client_id = client_id.strip()
        self.source = "runtime input"


_myanimelist_config: Optional[MyAnimeListAPIConfig] = None


def get_myanimelist_api_config() -> MyAnimeListAPIConfig:
    global _myanimelist_config
    if _myanimelist_config is None:
        _myanimelist_config = MyAnimeListAPIConfig()
    return _myanimelist_config


def _mask_value(value: str) -> str:
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:6]}...{value[-4:]}"


def setup_myanimelist_api_config() -> bool:
    """
    Ensure the MyAnimeList API client auth is available.

    Public anime score reads only need MAL client authentication, so the program
    uses X-MAL-CLIENT-ID by default. A built-in client ID is bundled, and it can
    be overridden with MAL_CLIENT_ID. A bearer token can also be supplied through
    MAL_ACCESS_TOKEN for future user-authenticated endpoints.
    """
    config = get_myanimelist_api_config()
    config.reload()

    if config.is_configured:
        if config.client_id:
            logging.info(
                "MyAnimeList API配置已加载 (%s): client_id=%s",
                config.source,
                _mask_value(config.client_id),
            )
        else:
            logging.info("MyAnimeList API配置已加载 (%s): 使用Bearer Token", config.source)
        return True

    logging.error("MyAnimeList API未配置Client ID")
    return False
