"""Files: nothing outside the home, whichever way a path tries to leave it."""
import pytest
from fastapi import HTTPException

from akari import files


def test_paths_inside_the_home_are_fine(home):
    (home / "Musik").mkdir()
    assert files.target("Musik") == (home / "Musik").resolve()
    assert files.target("") == home.resolve()
    assert files.place("/Musik/a.mp3") == home.resolve() / "Musik" / "a.mp3"   # a leading slash is still the home


@pytest.mark.parametrize("rel", ["..", "../etc/passwd", "Musik/../../etc", "a/../../b"])
def test_dot_dot_does_not_leave_the_home(home, rel):
    with pytest.raises(HTTPException) as e:
        files.place(rel)
    assert e.value.status_code == 403


def test_a_link_out_of_the_home_is_refused(home, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope")
    (home / "out").symlink_to(outside)
    files.place("out")                                   # the link itself is in the home …
    with pytest.raises(HTTPException) as e:
        files.target("out/secret.txt")                   # … where it leads is not
    assert e.value.status_code == 403
