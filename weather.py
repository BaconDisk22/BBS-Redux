"""OpenWeatherMap — the seam under the Weather utility.

`OpenWeather.current(location)` returns the API's current-conditions dict or
raises a `WeatherError` naming what went wrong. It is the only place that
touches the network; WeatherFlow formats what comes back, and its tests hand
it a fake with the same one method.
"""

import logging

import requests

API_URL = "https://api.openweathermap.org/data/2.5/weather"
TIMEOUT_SECONDS = 10

# WeatherError kinds — each one is a different reply to the node.
UNCONFIGURED = "unconfigured"
NOT_FOUND = "not_found"
BAD_KEY = "bad_key"
TIMEOUT = "timeout"
UNAVAILABLE = "unavailable"


class WeatherError(Exception):
    def __init__(self, kind, status=None):
        super().__init__(kind)
        self.kind = kind
        self.status = status


def query_params(location, api_key, units):
    """All-digit locations are US zip codes (leading zeros kept, e.g. 08260);
    anything else goes to the city search as "city,state" or "city,country"."""
    params = {"appid": api_key, "units": units}
    if location.isdigit():
        params["zip"] = f"{location},US"
    else:
        params["q"] = location
    return params


class OpenWeather:
    def __init__(self, config, get=requests.get):
        self._config = config
        self._get = get

    @property
    def default_location(self):
        return self._config.default_location

    @property
    def units(self):
        return self._config.units

    def current(self, location):
        if not self._config.api_key:
            raise WeatherError(UNCONFIGURED)
        params = query_params(location, self._config.api_key, self._config.units)
        try:
            response = self._get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            raise WeatherError(TIMEOUT)
        except requests.exceptions.RequestException as error:
            logging.error(f"Weather request failed: {error}")
            raise WeatherError(UNAVAILABLE)

        if response.status_code == 200:
            return response.json()
        if response.status_code == 404:
            raise WeatherError(NOT_FOUND, 404)
        if response.status_code == 401:
            raise WeatherError(BAD_KEY, 401)
        raise WeatherError(UNAVAILABLE, response.status_code)
