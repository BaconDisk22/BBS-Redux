"""Weather: the OpenWeather adapter and WeatherFlow, with no network."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import types

import requests

import weather as service
from flows.base import Deps, Keep
from flows.weather import WeatherFlow, report
from session import Session
from settings import WeatherConfig

SAMPLE = {
    "name": "North Wildwood",
    "main": {"temp": 71.26, "feels_like": 70.0, "temp_min": 68.0,
             "temp_max": 74.5, "humidity": 60},
    "weather": [{"description": "clear sky"}],
    "wind": {"speed": 8.04},
}


class FakeWeather:
    def __init__(self, data=SAMPLE, error=None, default_location="08260", units="imperial"):
        self.data, self.error = data, error
        self.default_location, self.units = default_location, units
        self.asked = []

    def current(self, location):
        self.asked.append(location)
        if self.error:
            raise self.error
        return self.data


def fake_get(status=200, payload=SAMPLE, raises=None, calls=None):
    def get(url, params=None, timeout=None):
        if calls is not None:
            calls.append((url, params, timeout))
        if raises:
            raise raises
        return types.SimpleNamespace(status_code=status, json=lambda: payload)
    return get


# --- the adapter -----------------------------------------------------------

def test_zip_codes_keep_their_leading_zero():
    params = service.query_params("08260", "k", "imperial")
    assert params["zip"] == "08260,US"
    assert "q" not in params


def test_city_names_use_the_city_search():
    params = service.query_params("Cape May,NJ,US", "k", "metric")
    assert params["q"] == "Cape May,NJ,US"
    assert params["units"] == "metric"


def test_adapter_uses_https_and_returns_the_json():
    calls = []
    api = service.OpenWeather(WeatherConfig(api_key="k"), get=fake_get(calls=calls))
    assert api.current("08260") == SAMPLE
    assert calls[0][0].startswith("https://")


def test_adapter_without_key_never_calls_out():
    calls = []
    api = service.OpenWeather(WeatherConfig(api_key=None), get=fake_get(calls=calls))
    try:
        api.current("08260")
    except service.WeatherError as error:
        assert error.kind == service.UNCONFIGURED
    else:
        raise AssertionError("expected WeatherError")
    assert calls == []


def _kind(get):
    try:
        service.OpenWeather(WeatherConfig(api_key="k"), get=get).current("x")
    except service.WeatherError as error:
        return error.kind, error.status
    raise AssertionError("expected WeatherError")


def test_adapter_maps_http_failures():
    assert _kind(fake_get(status=401)) == (service.BAD_KEY, 401)
    assert _kind(fake_get(status=404)) == (service.NOT_FOUND, 404)
    assert _kind(fake_get(status=500)) == (service.UNAVAILABLE, 500)


def test_adapter_maps_network_failures():
    assert _kind(fake_get(raises=requests.exceptions.Timeout()))[0] == service.TIMEOUT
    assert _kind(fake_get(raises=requests.exceptions.ConnectionError()))[0] == service.UNAVAILABLE


def test_placeholder_key_in_config_counts_as_no_key():
    import settings
    assert settings._api_key("your_api_key_here") is None
    assert settings._api_key("  ") is None
    assert settings._api_key(" abc ") == "abc"


# --- the flow --------------------------------------------------------------

def test_report_formats_imperial():
    text = report("08260", Deps(weather=FakeWeather()))
    assert text.startswith("🌤️ Weather for North Wildwood 🌤️")
    assert "Condition: Clear Sky" in text
    assert "Temp: 71.3°F" in text
    assert "High/Low: 74.5/68.0°F" in text
    assert "Wind: 8.0 mph" in text


def test_report_formats_metric():
    text = report("x", Deps(weather=FakeWeather(units="metric")))
    assert "°C" in text and "m/s" in text


def test_no_location_uses_the_default():
    fake = FakeWeather()
    report(None, Deps(weather=fake))
    assert fake.asked == ["08260"]


def test_errors_become_replies():
    def reply(error):
        return report("Nowhere", Deps(weather=FakeWeather(error=error)))
    assert "not found" in reply(service.WeatherError(service.NOT_FOUND, 404))
    assert "Invalid API key" in reply(service.WeatherError(service.BAD_KEY, 401))
    assert "not configured" in reply(service.WeatherError(service.UNCONFIGURED))
    assert "timeout" in reply(service.WeatherError(service.TIMEOUT))
    assert "503" in reply(service.WeatherError(service.UNAVAILABLE, 503))


def test_malformed_payload_is_an_error_reply_not_a_crash():
    text = report("x", Deps(weather=FakeWeather(data={"main": {}})))
    assert text == "❌ Error retrieving weather."


def test_no_weather_service_is_unconfigured():
    assert "not configured" in report("x", Deps(weather=None))


def test_quick_command_parses_the_location():
    for message, expected in [("WX", "08260"), ("wx,08260", "08260"),
                              ("WX,,Cape May,NJ,US", "Cape May,NJ,US"),
                              ("wx, 19103", "19103")]:
        fake = FakeWeather()
        result = WeatherFlow().quick(message, Deps(weather=fake))
        assert fake.asked == [expected], message
        assert isinstance(result.outcome, Keep)


def test_session_routes_wx_from_anywhere():
    fake = FakeWeather()
    session = Session()
    out = session.advance(1, "WX,90210", Deps(weather=fake))
    assert fake.asked == ["90210"]
    assert out[0][1].startswith("🌤️")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"ok  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
