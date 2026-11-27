"""The clock widget's weather (weather.py): which city a time zone names, what a weather code looks like."""
import pytest

from akari import weather


@pytest.mark.parametrize("zone,city", [
    ("Europe/Berlin", "Berlin"), ("America/New_York", "New York"), ("America/Argentina/Buenos_Aires", "Buenos Aires"),
    ("UTC", None), ("Etc/UTC", None), ("", None),
])
def test_the_city_in_a_time_zone(zone, city):
    assert weather.zone_city(zone) == city


@pytest.mark.parametrize("code,kind", [(0, "clear"), (2, "partly"), (3, "cloudy"), (45, "fog"), (61, "rain"), (81, "rain"),
                                       (73, "snow"), (95, "storm"), (12345, "cloudy")])
def test_weather_codes(code, kind):
    assert weather.kind(code) == kind
