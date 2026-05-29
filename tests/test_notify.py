import pytest

from app.db.connection import connect, init_db
from app.db.repository import Repository
from app.services.notify import notify, NotifyError


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    r = Repository(connect(db))
    r.insert_signal({"code": "600519", "name": "茅台", "signal_type": "golden_cross",
                     "level": "high", "snapshot_time": "2026-05-29 10:00:00", "detail": "d"})
    return r


def test_notify_sends_new_signals_once(repo):
    sent = []
    notify(repo, lambda to, subj, body: sent.append(to), ["a@x.com"])
    assert sent == ["a@x.com"]
    notify(repo, lambda to, subj, body: sent.append(to), ["a@x.com"])
    assert sent == ["a@x.com"]  # already notified -> no resend


def test_notify_records_failure_and_raises(repo):
    def boom(to, subj, body):
        raise RuntimeError("smtp down")
    with pytest.raises(NotifyError):
        notify(repo, boom, ["a@x.com"])
    sent = []
    notify(repo, lambda to, subj, body: sent.append(to), ["a@x.com"])
    assert sent == ["a@x.com"]  # failure logged, retry still attempted
