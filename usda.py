"""
usda.py — USDA FoodData Central API wrapper.

Usage:
  python usda.py search "<query>"
  python usda.py get_food <fdc_id>

Reads USDA_API_KEY from environment. Prints raw JSON to stdout.
"""

import json
import os
import sys

import requests


BASE_URL = "https://api.nal.usda.gov/fdc/v1"


def get_api_key() -> str:
    key = os.environ.get("USDA_API_KEY")
    if not key:
        print(json.dumps({"error": "USDA_API_KEY environment variable is not set"}))
        sys.exit(1)
    return key


def search(query: str) -> None:
    key = get_api_key()
    url = f"{BASE_URL}/foods/search"
    params = {"query": query, "api_key": key, "pageSize": 10}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # Return the foods array
    print(json.dumps(data.get("foods", [])))


def get_food(fdc_id: str) -> None:
    key = get_api_key()
    url = f"{BASE_URL}/food/{fdc_id}"
    params = {"api_key": key}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    print(json.dumps(resp.json()))


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: usda.py <search|get_food> [args]"}))
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "search":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Usage: usda.py search <query>"}))
            sys.exit(1)
        search(sys.argv[2])
    elif cmd == "get_food":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Usage: usda.py get_food <fdc_id>"}))
            sys.exit(1)
        get_food(sys.argv[2])
    else:
        print(json.dumps({"error": f"Unknown command: {cmd}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
