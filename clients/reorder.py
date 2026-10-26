"""Offline example of a legacy warehouse terminal integration."""

import httpx


def fetch_catalog(base_url: str):
    response = httpx.get(f"{base_url}/v1/items", timeout=5)
    response.raise_for_status()
    return response.json()
