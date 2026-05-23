import pytest

from app.core import audit


class CallerSession:
    committed = False

    async def commit(self):
        self.committed = True


class AuditSession:
    def __init__(self):
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def execute(self, *_args, **_kwargs):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None


@pytest.mark.asyncio
async def test_audit_log_does_not_commit_caller_session(monkeypatch):
    monkeypatch.setattr("app.db.session.async_session", lambda: AuditSession())
    caller = CallerSession()
    await audit.audit_log(caller, "invoice.created")
    assert caller.committed is False
