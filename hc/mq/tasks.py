"""Задачи, которые выполняет consumer: вызовы двух публичных API.

API взяты из https://github.com/public-apis/public-apis (без ключей и auth):
  * Cat Facts  — https://catfact.ninja
  * Open-Meteo — https://open-meteo.com

Только стандартная библиотека, чтобы модуль одинаково работал и в контейнере
приложения, и на машине разработчика без pycurl/Django.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

USER_AGENT = "healthchecks-mq/1.0"
TIMEOUT = 10  # seconds


def _get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cat_fact() -> dict[str, Any]:
    """Случайный факт о кошках."""
    data = _get_json("https://catfact.ninja/fact")
    return {"fact": data["fact"], "length": data["length"]}


def weather(latitude: float = 55.79, longitude: float = 49.11) -> dict[str, Any]:
    """Текущая погода по координатам (по умолчанию — Казань)."""
    data = _get_json(
        "https://api.open-meteo.com/v1/forecast",
        {"latitude": latitude, "longitude": longitude, "current_weather": "true"},
    )
    cw = data["current_weather"]
    return {
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "time": cw["time"],
        "temperature_c": cw["temperature"],
        "windspeed_kmh": cw["windspeed"],
        "weathercode": cw["weathercode"],
    }


# Имя задачи в сообщении -> функция. Producer проверяет имя по этому же словарю.
TASKS: dict[str, Callable[..., dict[str, Any]]] = {
    "cat_fact": cat_fact,
    "weather": weather,
}


def run_task(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        func = TASKS[name]
    except KeyError:
        raise ValueError(f"Unknown task: {name!r}, known: {sorted(TASKS)}") from None
    return func(**(args or {}))
