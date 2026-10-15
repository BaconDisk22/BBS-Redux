"""Weather: current conditions from OpenWeatherMap, as one reply.

A leaf, not a conversation — Weathe[R] on the Utilities menu answers for the
configured default location, and the WX quick command answers for the default
or for a location given after it (``WX,08260`` / ``WX,,Cape May,NJ,US``).

Pure: the fetch goes through the injected ``deps.weather`` service (see
weather.py), so the tests hand in a fake and never touch the network.
"""

import weather as service
from flows.base import keep

QUICK_USAGE = "Weather Quick Command format:\nWX or WX,{zip or city,state,country}"

_ERRORS = {
    service.UNCONFIGURED: "⚠️ Weather service not configured. Please set API key in config.ini",
    service.BAD_KEY: "⚠️ Invalid API key. Please check config.ini",
    service.TIMEOUT: "❌ Weather service timeout. Please try again.",
}


def report(location, deps):
    """The reply for one location; the configured default when none is given."""
    if deps.weather is None:
        return _ERRORS[service.UNCONFIGURED]
    location = (location or "").strip() or _default_location(deps)
    try:
        data = deps.weather.current(location)
    except service.WeatherError as error:
        if error.kind == service.NOT_FOUND:
            return f"❌ Location '{location}' not found. Try zip code or city,state format."
        if error.kind in _ERRORS:
            return _ERRORS[error.kind]
        if error.status:
            return f"❌ Weather service error: {error.status}"
        return "❌ Unable to fetch weather data."
    try:
        return format_report(data, _units(deps))
    except (KeyError, IndexError, TypeError, ValueError):
        return "❌ Error retrieving weather."


def format_report(data, units):
    temp_unit = "°F" if units == "imperial" else "°C"
    wind_unit = "mph" if units == "imperial" else "m/s"
    main = data["main"]
    return (
        f"🌤️ Weather for {data.get('name', 'Unknown')} 🌤️\n"
        f"Condition: {data['weather'][0]['description'].title()}\n"
        f"Temp: {main['temp']:.1f}{temp_unit}\n"
        f"Feels Like: {main['feels_like']:.1f}{temp_unit}\n"
        f"High/Low: {main['temp_max']:.1f}/{main['temp_min']:.1f}{temp_unit}\n"
        f"Humidity: {main['humidity']}%\n"
        f"Wind: {data['wind']['speed']:.1f} {wind_unit}"
    )


def _default_location(deps):
    return getattr(deps.weather, "default_location", "") or ""


def _units(deps):
    return getattr(deps.weather, "units", "imperial")


class WeatherFlow:
    """Owns only the WX quick command; the menu entry is a Navigation leaf."""

    TOPICS = []
    QUICK_COMMANDS = {"wx,,": "quick"}

    def quick(self, message, deps):
        """WX, WX,location or WX,,location — the separator is forgiving here
        because a location can itself contain commas."""
        location = message.strip()[2:].lstrip(", ").strip()
        return keep(replies=[report(location, deps)])
