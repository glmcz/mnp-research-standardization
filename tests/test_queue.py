"""The work queue: many workers, disjoint claims, no lost work.

These are the invariants that the first corpus run violated — two workers were handed the
same paper (duplicate effort, /tmp collisions), and ten workers died to a rate limit with
their work neither done nor returned.

Integration tests need a PostgreSQL server. `tool/test_db.sh` starts a throwaway one; when
none is reachable they skip rather than fail, so the suite never depends on local state.
"""

import os

import pytest

from mnp import queue as q

pytestmark = pytest.mark.skipif(not q.available(), reason="no PostgreSQL reachable")


@pytest.fixture
def wq(tmp_path):
    """A queue in its own schema, dropped afterwards."""
    with q.Queue(schema=f"mnp_test_{os.getpid()}") as w:
        w.reset()
        yield w
        w.drop()


PAPERS = [f"PMC{i:04d}" for i in range(1, 21)]


def test_init_is_idempotent(wq):
    assert wq.init(PAPERS, run_id="r1", brief_sha="abc") == 20
    assert wq.init(PAPERS, run_id="r1", brief_sha="abc") == 0
    assert wq.status()["pending"] == 20


def test_two_workers_never_receive_the_same_paper(wq):
    wq.init(PAPERS, run_id="r1", brief_sha="abc")
    a = wq.claim("worker-a", n=8)
    b = wq.claim("worker-b", n=8)
    assert len(a) == 8 and len(b) == 8
    assert set(a).isdisjoint(b)
    assert wq.status()["leased"] == 16
    assert wq.status()["pending"] == 4


def test_a_claim_larger_than_the_queue_takes_what_is_left(wq):
    wq.init(PAPERS[:3], run_id="r1", brief_sha="abc")
    assert len(wq.claim("worker-a", n=10)) == 3
    assert wq.claim("worker-b", n=10) == []


def test_claims_are_ordered_so_a_rebuilt_queue_assigns_the_same_way(wq):
    wq.init(PAPERS, run_id="r1", brief_sha="abc")
    first = wq.claim("worker-a", n=5)
    wq.reset()
    wq.init(PAPERS, run_id="r1", brief_sha="abc")
    assert wq.claim("worker-z", n=5) == first


def test_done_marks_only_what_the_worker_holds(wq):
    wq.init(PAPERS, run_id="r1", brief_sha="abc")
    a = wq.claim("worker-a", n=5)
    b = wq.claim("worker-b", n=5)
    assert wq.done("worker-a", a) == 5
    # worker-a cannot close worker-b's papers
    assert wq.done("worker-a", b) == 0
    s = wq.status()
    assert s["done"] == 5 and s["leased"] == 5


def test_an_expired_lease_returns_the_work_and_counts_the_attempt(wq):
    wq.init(PAPERS[:4], run_id="r1", brief_sha="abc")
    claimed = wq.claim("worker-dead", n=4, lease_seconds=-1)  # already expired
    assert len(claimed) == 4
    assert wq.reap() == 4
    s = wq.status()
    assert s["pending"] == 4 and s["leased"] == 0
    assert wq.claim("worker-b", n=4) == claimed  # same papers, fresh worker
    assert wq.attempts(claimed[0]) == 1


def test_a_live_lease_is_not_reaped(wq):
    wq.init(PAPERS[:4], run_id="r1", brief_sha="abc")
    wq.claim("worker-a", n=4, lease_seconds=600)
    assert wq.reap() == 0
    assert wq.status()["leased"] == 4


def test_work_that_keeps_failing_stops_being_retried(wq):
    wq.init(PAPERS[:1], run_id="r1", brief_sha="abc")
    for _ in range(3):
        wq.claim("worker-dead", n=1, lease_seconds=-1)
        wq.reap()
    assert wq.status().get("failed") == 1
    assert wq.claim("worker-b", n=1) == []


def test_a_brief_change_is_visible_per_paper(wq):
    wq.init(PAPERS[:2], run_id="r1", brief_sha="abc")
    got = wq.claim("worker-a", n=2)
    wq.done("worker-a", got, brief_sha="def")
    assert wq.brief_of(got[0]) == "def"


def test_status_counts_every_state(wq):
    wq.init(PAPERS[:6], run_id="r1", brief_sha="abc")
    got = wq.claim("worker-a", n=4)
    wq.done("worker-a", got[:2])
    wq.fail(got[2], "unreadable XML")
    s = wq.status()
    assert s["done"] == 2 and s["failed"] == 1 and s["leased"] == 1 and s["pending"] == 2


def test_parallel_workers_partition_the_corpus_with_no_overlap(wq):
    """The first run's actual failure: two workers handed the same papers. Eight processes
    claim at once; every paper must go to exactly one of them."""
    import json
    import subprocess
    import sys

    wq.init([f"PMC{i:04d}" for i in range(1, 81)], run_id="r1", brief_sha="abc")
    script = (
        "import json,sys;from mnp.queue import Queue;"
        f"w=Queue(schema={wq.schema!r});w.__enter__();"
        "print(json.dumps(w.claim(sys.argv[1], n=10)))"
    )
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", script, f"worker-{i}"],
            stdout=subprocess.PIPE,
            env={**os.environ},
        )
        for i in range(8)
    ]
    claims = [json.loads(p.communicate()[0]) for p in procs]
    assert all(p.returncode == 0 for p in procs)
    flat = [pmcid for c in claims for pmcid in c]
    assert len(flat) == 80, "every paper should be claimed exactly once"
    assert len(set(flat)) == 80, "a paper was handed to two workers"
    assert wq.status()["pending"] == 0
