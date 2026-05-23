import inspect

from app.api import auth


def test_auth_dependency_does_not_commit():
    source = inspect.getsource(auth._auth_via_api_key)
    assert "db.commit" not in source
