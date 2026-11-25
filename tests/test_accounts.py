"""Account names: what Linux and Akari both accept."""
import pytest

from akari import accounts


@pytest.mark.parametrize("name", ["ada", "lucya", "a1", "dev-ops", "max_mustermann", "a" * 32])
def test_good_names(name):
    assert accounts.NAME_RE.match(name)


@pytest.mark.parametrize("name", ["", "a", "Ada", "1ada", "-ada", "ad a", "ada.b", "a" * 33, "ädä", "ada\n"])
def test_bad_names(name):
    assert not accounts.NAME_RE.match(name)          # as the code asks
