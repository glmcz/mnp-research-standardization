import json

import httpx
import pytest

from mnp.corpus import epmc


def _page(records, next_cursor):
    body = {
        "hitCount": 3,
        "nextCursorMark": next_cursor,
        "resultList": {"result": records},
    }
    return httpx.Response(200, json=body)


def _rec(pmcid, doi, oa="Y", year="2020", journal="J"):
    r = {
        "id": pmcid or doi,
        "doi": doi,
        "pubYear": year,
        "journalTitle": journal,
        "isOpenAccess": oa,
        "title": "t",
        "pubType": "research-article",
    }
    if pmcid:
        r["pmcid"] = pmcid
    return r


@pytest.fixture
def ua(monkeypatch):
    monkeypatch.setenv("MNP_CONTACT_EMAIL", "test@example.org")


def test_search_pages_with_cursor_mark_and_stops_when_the_cursor_repeats(tmp_path, ua):
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        cursor = request.url.params["cursorMark"]
        if cursor == "*":
            return _page([_rec("PMC1", "10.1/a"), _rec("PMC2", "10.1/b")], "C1")
        if cursor == "C1":
            return _page([_rec("PMC3", "10.1/c")], "C2")
        # Europe PMC returns the same cursor forever at the end of the result set
        return _page([], "C2")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    api = epmc.EuropePMC(
        client, search_dir=tmp_path, xml_dir=tmp_path / "xml", sleep=lambda s: None
    )
    records = api.search("q", page_size=2)
    assert [r["pmcid"] for r in records] == ["PMC1", "PMC2", "PMC3"]
    assert [p["cursorMark"] for p in seen] == ["*", "C1", "C2"]
    assert seen[0]["pageSize"] == "2"
    assert seen[0]["resultType"] == "lite"
    assert seen[0]["format"] == "json"
    pages = sorted(tmp_path.glob("page_*.json"))
    assert len(pages) == 3
    assert json.loads(pages[0].read_text())["nextCursorMark"] == "C1"


def test_search_sends_the_contact_user_agent(tmp_path, ua):
    agents = []

    def handler(request):
        agents.append(request.headers["user-agent"])
        return _page([], "*")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    epmc.EuropePMC(client, search_dir=tmp_path, xml_dir=tmp_path, sleep=lambda s: None).search("q")
    assert agents and "mailto:test@example.org" in agents[0]


def test_client_refuses_to_start_without_a_contact_email(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: _page([], "*")))
    with pytest.raises(epmc.MissingConfig):
        epmc.EuropePMC(client, search_dir=tmp_path, xml_dir=tmp_path)


def test_records_to_frame_keeps_pmcid_rows_and_dedupes_on_doi():
    records = [
        _rec("PMC1", "10.1/a"),
        _rec("PMC1b", "10.1/A"),  # same DOI, different case: a duplicate
        _rec(None, "10.1/nopmc"),  # no full text available
        _rec("PMC3", None),  # no DOI: keep, cannot be a duplicate of anything
        _rec("PMC4", "10.1/d", oa="N"),
    ]
    df = epmc.records_to_frame(records)
    assert list(df["pmcid"]) == ["PMC1", "PMC3", "PMC4"]
    assert list(df["is_oa"]) == [True, True, False]
    assert set(df.columns) >= {"pmcid", "doi", "year", "journal", "is_oa", "title", "pub_type"}
    assert df["year"].dtype.kind == "i"


def test_fetch_writes_xml_and_a_second_call_is_served_from_cache(tmp_path, ua):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=b"<article><body>x</body></article>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    api = epmc.EuropePMC(
        client, search_dir=tmp_path, xml_dir=tmp_path / "xml", sleep=lambda s: None
    )
    p1 = api.fetch_full_text("PMC1")
    p2 = api.fetch_full_text("PMC1")
    assert p1 == p2 == tmp_path / "xml" / "PMC1.xml"
    assert p1.read_bytes().startswith(b"<article>")
    assert len(calls) == 1
    assert calls[0].endswith("/PMC1/fullTextXML")


def test_fetch_treats_an_empty_cached_file_as_a_miss(tmp_path, ua):
    (tmp_path / "xml").mkdir()
    (tmp_path / "xml" / "PMC1.xml").write_bytes(b"")
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<article/>"))
    )
    api = epmc.EuropePMC(
        client, search_dir=tmp_path, xml_dir=tmp_path / "xml", sleep=lambda s: None
    )
    assert api.fetch_full_text("PMC1").read_bytes() == b"<article/>"


def test_fetch_retries_on_429_and_5xx_then_logs_the_failure(tmp_path, ua):
    attempts = {"PMC1": 0, "PMC2": 0}
    slept = []

    def handler(request):
        pmcid = request.url.path.split("/")[-2]
        attempts[pmcid] += 1
        if pmcid == "PMC1":
            return (
                httpx.Response(429) if attempts[pmcid] < 3 else httpx.Response(200, content=b"<a/>")
            )
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    api = epmc.EuropePMC(
        client, search_dir=tmp_path, xml_dir=tmp_path / "xml", sleep=slept.append, max_retries=3
    )
    assert api.fetch_full_text("PMC1") is not None
    assert attempts["PMC1"] == 3
    assert api.fetch_full_text("PMC2") is None
    assert attempts["PMC2"] == 3
    assert not (tmp_path / "xml" / "PMC2.xml").exists()
    log = (tmp_path / "xml" / "fetch_log.csv").read_text()
    assert "PMC2,503" in log
    assert any(s > 0 for s in slept), "backoff must actually wait"


def test_fetch_does_not_cache_a_404(tmp_path, ua):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    api = epmc.EuropePMC(
        client, search_dir=tmp_path, xml_dir=tmp_path / "xml", sleep=lambda s: None
    )
    assert api.fetch_full_text("PMC9") is None
    assert not (tmp_path / "xml" / "PMC9.xml").exists()


def test_rate_limiter_spaces_requests_to_the_configured_rate(tmp_path, ua):
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<a/>"))
    )
    api = epmc.EuropePMC(
        client,
        search_dir=tmp_path,
        xml_dir=tmp_path / "xml",
        sleep=sleep,
        clock=lambda: now[0],
        rate_per_s=5,
    )
    for i in range(3):
        api.fetch_full_text(f"PMC{i}")
    assert sum(slept) == pytest.approx(0.4, abs=1e-6)


def test_hit_count_reads_the_header_count(ua):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: _page([], "*")))
    assert epmc.hit_count(client, "q") == 3


def test_query_variants_strip_the_oa_filter_for_the_all_denominator():
    q = 'foo AND OPEN_ACCESS:y AND NOT PUB_TYPE:"review"'
    assert epmc.without_oa_filter(q) == 'foo AND NOT PUB_TYPE:"review"'
    assert epmc.without_oa_filter("foo") == "foo"
