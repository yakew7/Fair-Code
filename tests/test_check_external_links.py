"""scripts/check_external_links.py classifies links and never fails the repository's checks (#1127)."""

import http.server
import importlib
import io
import json
import threading
import urllib.error

import pytest

script = importlib.import_module("scripts.check_external_links")


class _Handler(http.server.BaseHTTPRequestHandler):
    requests = []
    flaky_seen = set()

    def _respond(self):
        user_agent = self.headers.get("User-Agent", "")
        self.requests.append((self.path, self.command, user_agent))
        if self.path == "/flaky":
            code = 200 if self.path in self.flaky_seen else 503
            self.flaky_seen.add(self.path)
        elif self.path == "/always404":
            code = 404
        elif self.path == "/kaggle":
            code = 200 if "Chrome/" in user_agent and "FairCodeLinkCheck/1.0" in user_agent else 404
        else:
            code = {"/ok": 200, "/gone": 404, "/removed": 410, "/blocked": 403, "/slow-down": 429, "/down": 503,
                    "/nohead": 200}.get(self.path, 404)
        if self.path == "/nohead" and self.command == "HEAD":
            code = 405
        redirects = {"/redirect": (302, "/ok"), "/temporary": (307, "/ok"), "/moved": (301, "/ok"),
                     "/moved-permanently": (308, "/ok"), "/moved-twice": (301, "/redirect"),
                     "/moved-to-gone": (301, "/gone")}
        if self.path in redirects:
            status, location = redirects[self.path]
            self.send_response(status)
            self.send_header("Location", location)
            self.end_headers()
            return
        self.send_response(code)
        self.end_headers()

    do_GET = do_HEAD = _respond

    def log_message(self, *args):
        pass


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(script, "RETRY_DELAY", 0.0)


@pytest.fixture(scope="module")
def server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    thread.join()


@pytest.mark.parametrize("path,kind", [("/ok", "ok"), ("/redirect", "ok"), ("/temporary", "ok"), ("/nohead", "ok"),
                                       ("/moved", "moved"), ("/moved-permanently", "moved"), ("/gone", "broken"),
                                       ("/removed", "broken"), ("/blocked", "unknown"), ("/slow-down", "unknown"),
                                       ("/down", "unknown")])
def test_each_status_class(server, path, kind):
    assert script.check_url(server + path, timeout=5)[0] == kind


def test_404_retries_once_with_project_browser_user_agent(server):
    _Handler.requests.clear()

    assert script.check_url(server + "/kaggle", timeout=5) == ("ok", "200")

    requests = [request for request in _Handler.requests if request[0] == "/kaggle"]
    assert [(request[1], request[2]) for request in requests] == [
        ("HEAD", script.USER_AGENT),
        ("GET", script.BROWSER_USER_AGENT),
    ]
    assert len(requests) == 2


def test_404_stays_broken_after_the_single_retry(server):
    _Handler.requests.clear()

    assert script.check_url(server + "/always404", timeout=5) == ("broken", "404")
    assert len([request for request in _Handler.requests if request[0] == "/always404"]) == 2


@pytest.mark.parametrize(
    "resolver_body,expected",
    [
        (b'{"responseCode": 1}', ("ok", "DOI exists")),
        (b'{"responseCode": 100}', ("broken", "DOI not found")),
        (b'{"responseCode": 200}', ("broken", "DOI has no resolution values")),
        (b'{"responseCode": 2}', ("unknown", "DOI resolver response 2")),
    ],
)
def test_403_doi_page_uses_handle_resolver(monkeypatch, resolver_body, expected):
    calls = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return resolver_body

    def fake_urlopen(request, **_kwargs):
        calls.append(request.full_url)
        if request.full_url.startswith("https://doi.org/api/handles/"):
            return Response()
        raise urllib.error.HTTPError(request.full_url, 403, "blocked", {}, io.BytesIO())

    monkeypatch.setattr(script.urllib.request, "urlopen", fake_urlopen)

    assert script.check_url("https://publisher.example/doi/10.1234/example", timeout=1) == expected
    assert calls == [
        "https://publisher.example/doi/10.1234/example",
        "https://doi.org/api/handles/10.1234/example",
    ]


def test_missing_doi_is_broken_when_resolver_returns_404(monkeypatch):
    def fake_urlopen(request, **_kwargs):
        if request.full_url.startswith("https://doi.org/api/handles/"):
            raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, io.BytesIO())
        raise urllib.error.HTTPError(request.full_url, 403, "blocked", {}, io.BytesIO())

    monkeypatch.setattr(script.urllib.request, "urlopen", fake_urlopen)

    assert script.check_url("https://publisher.example/doi/10.1234/missing", timeout=1) == (
        "broken", "DOI not found"
    )


def test_a_name_that_does_not_resolve_is_broken_and_a_refused_connection_is_unknown():
    assert script.check_url("http://this-host-does-not-exist.invalid/page", timeout=5)[0] == "broken"
    assert script.check_url("http://127.0.0.1:9/", timeout=5)[0] == "unknown"


def test_collect_urls_finds_markdown_and_bare_links_and_skips_local_hosts(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("See [a](https://example.org/a), <https://example.org/b> and [local](http://localhost:8000/x).\n"
                   "Again [a](https://example.org/a). A [relative](other.md) link is ignored.\n", encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text("[a](https://example.org/a)\n", encoding="utf-8")
    found = script.collect_urls([doc, other])
    assert set(found) == {"https://example.org/a", "https://example.org/b"}
    assert len(found["https://example.org/a"]) == 2


def test_main_reports_without_failing_unless_asked(server, tmp_path, capsys):
    doc = tmp_path / "doc.md"
    doc.write_text(f"[ok]({server}/ok) [gone]({server}/gone) [blocked]({server}/blocked)\n", encoding="utf-8")
    assert script.main([str(doc), "--timeout", "5", "--check-local"]) == 0
    out = capsys.readouterr().out
    assert "1 ok, 1 broken, 1 unknown" in out and f"{server}/gone" in out
    assert script.main([str(doc), "--timeout", "5", "--fail-on-broken", "--check-local"]) == 1
    capsys.readouterr()
    assert script.main([str(doc), "--timeout", "5", "--json", "--limit", "2", "--check-local"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checked"] == 2 and set(report) == {
        "checked", "ok", "moved", "broken", "unknown", "ignored", "stale_ignored", "checked_by_hand", "expired_ignored"
    }


def test_ignore_list_skips_a_url_and_reports_it(server, tmp_path, capsys):
    doc = tmp_path / "doc.md"
    doc.write_text(f"[ok]({server}/ok) [gone]({server}/gone)\n", encoding="utf-8")
    ignore = tmp_path / "ignore.txt"
    ignore.write_text(f"# a comment\n\n{server}/gone needs a login\n{server}/retired no longer referenced\n", encoding="utf-8")
    assert script.main([str(doc), "--timeout", "5", "--check-local", "--ignore-file", str(ignore)]) == 0
    out = capsys.readouterr().out
    assert "0 broken" in out and "1 ignored" in out and "(needs a login)" in out
    assert "Stale ignored URLs (1 not found in checked documents)" in out
    assert f"{server}/retired  (no longer referenced)" in out
    assert script.main([str(doc), "--timeout", "5", "--check-local", "--json", "--ignore-file", str(ignore)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checked"] == 1 and [item["url"] for item in report["ignored"]] == [f"{server}/gone"]
    assert report["ignored"][0]["files"] == [str(doc)]
    assert report["stale_ignored"] == [{"url": f"{server}/retired", "reason": "no longer referenced"}]
    assert "1 stale ignore-list entry" in script.render_issue_body(report)
    assert "remove stale ignore-list entries" in script.render_issue_body(report)
    assert script.report_needs_issue(report)


def test_weekly_issue_state_closes_only_when_broken_and_stale_lists_are_empty():
    assert script.report_needs_issue({"broken": [], "stale_ignored": []}) is False
    assert script.report_needs_issue({"broken": [{"url": "https://example.org/gone"}], "stale_ignored": []}) is True
    assert script.report_needs_issue({"broken": [], "stale_ignored": [{"url": "https://example.org/old"}]}) is True


def test_ignore_list_requires_a_reason_and_tolerates_a_missing_file(tmp_path):
    bad = tmp_path / "ignore.txt"
    bad.write_text("https://example.org/a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ignore.txt:1"):
        script.load_ignore_list(bad)
    assert script.load_ignore_list(tmp_path / "missing.txt") == {}


def test_the_committed_ignore_list_parses_and_names_the_two_known_links():
    ignored = script.load_ignore_list()
    assert "https://github.com/TanishGoyal-Dev" in ignored
    assert "https://github.com/yakew7/Fair-Code/security/code-scanning" in ignored


def _archive_responder(body):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return body

    def fake_urlopen(request, **_kwargs):
        if request.full_url.startswith("https://archive.org/wayback/available?url="):
            if body is None:
                raise urllib.error.URLError("offline")
            return Response()
        raise urllib.error.HTTPError(request.full_url, 403, "blocked", {}, io.BytesIO())

    return fake_urlopen


@pytest.mark.parametrize(
    "body,expected",
    [
        (b'{"archived_snapshots": {"closest": {"available": true, "url": "https://web.archive.org/x"}}}',
         ("unknown", "403 (archived copy exists)")),
        (b'{"archived_snapshots": {}}', ("unknown", "403 (no archive copy)")),
        (b"not json", ("unknown", "403")),
        (None, ("unknown", "403")),
    ],
)
def test_403_page_is_checked_against_the_internet_archive(monkeypatch, body, expected):
    # #1195: still unknown, never broken, but the report can tell archived from unarchived
    monkeypatch.setattr(script.urllib.request, "urlopen", _archive_responder(body))
    assert script.check_url("https://journal.example.org/article/1", timeout=1) == expected


def test_a_local_403_never_asks_the_internet_archive(server):
    assert script.check_url(server + "/blocked", timeout=5) == ("unknown", "403")


def test_render_splits_unverified_403_links_out_of_the_unknown_list():
    report = {"checked": 2, "ok": [], "moved": [], "broken": [], "ignored": [], "stale_ignored": [],
              "unknown": [{"url": "https://a.example/x", "detail": "403 (archived copy exists)", "files": ["a.md"]},
                          {"url": "https://b.example/y", "detail": "403 (no archive copy)", "files": ["b.md"]}]}
    out = script.render(report)
    unknown_block, unverified_block = out.split("Unverified")
    assert "https://a.example/x" in unknown_block and "https://b.example/y" not in unknown_block
    assert "https://b.example/y" in unverified_block
    assert "1 of those answered 403 and have no Internet Archive copy" in script.render_issue_body(report)


def test_collect_urls_keeps_balanced_parentheses_in_a_url(tmp_path):
    # #1229: the link ended at the first ")" so S0895-4356(15 was checked instead of the real address
    doc = tmp_path / "doc.md"
    doc.write_text("[a](https://example.org/article/S0895-4356(15)00001-X/fulltext) and [b](https://example.org/b), "
                   "and (see [c](https://example.org/c)).\n", encoding="utf-8")
    assert set(script.collect_urls([doc])) == {
        "https://example.org/article/S0895-4356(15)00001-X/fulltext", "https://example.org/b", "https://example.org/c"}


def test_a_transient_503_is_retried_once_and_a_lasting_one_stays_unknown(server):
    # #1231
    _Handler.flaky_seen.clear()
    _Handler.requests.clear()
    assert script.check_url(server + "/flaky", timeout=5) == ("ok", "200")
    assert len([r for r in _Handler.requests if r[0] == "/flaky"]) == 2

    _Handler.requests.clear()
    assert script.check_url(server + "/down", timeout=5) == ("unknown", "503")
    assert len([r for r in _Handler.requests if r[0] == "/down" and r[1] == "HEAD"]) == 2


def test_retry_after_is_honoured_up_to_a_cap():
    def error(value):
        return urllib.error.HTTPError("http://x", 429, "slow", {"Retry-After": value} if value else {}, io.BytesIO())

    assert script._retry_delay(error("3")) == 3.0
    assert script._retry_delay(error("9999")) == script.RETRY_AFTER_CAP
    assert script._retry_delay(error("Wed, 21 Oct 2026 07:28:00 GMT")) == script.RETRY_DELAY
    assert script._retry_delay(error(None)) == script.RETRY_DELAY


def test_run_never_sends_more_than_the_per_host_limit_at_once(monkeypatch):
    import threading
    import time as time_module
    active, peak, lock = 0, 0, threading.Lock()

    def slow_check(url, timeout):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time_module.sleep(0.05)
        with lock:
            active -= 1
        return "ok", "200"

    monkeypatch.setattr(script, "check_url", slow_check)
    urls = {f"https://same.example.org/{n}": ["a.md"] for n in range(8)}
    report = script.run(urls, workers=8)
    assert len(report["ok"]) == 8 and peak <= script.PER_HOST_REQUESTS


def test_a_host_entry_skips_every_url_on_that_host_and_is_reported(tmp_path):
    # #1233
    ignore = tmp_path / "ignore.txt"
    ignore.write_text("host:Blocked.Example.org publisher answers every script with 403\n"
                      "host:unused.example.org nothing cites it\n"
                      "https://other.example.org/page one exact page\n", encoding="utf-8")
    entries = script.load_ignore_list(ignore)
    assert set(entries) == {"host:blocked.example.org", "host:unused.example.org", "https://other.example.org/page"}

    urls = {"https://blocked.example.org/a": ["a.md"], "https://blocked.example.org/b": ["b.md"],
            "https://other.example.org/page": ["a.md"]}
    report = script.run(urls, ignore=entries)
    assert report["checked"] == 0
    assert sorted(item["url"] for item in report["ignored"]) == sorted(urls)
    assert [item["url"] for item in report["stale_ignored"]] == ["host:unused.example.org"]


def test_a_malformed_host_entry_is_rejected(tmp_path):
    ignore = tmp_path / "ignore.txt"
    ignore.write_text("host:https://x.example.org reason\n", encoding="utf-8")
    with pytest.raises(ValueError, match="host:name reason"):
        script.load_ignore_list(ignore)


def test_retry_delay_and_per_host_options_are_used(server, tmp_path, monkeypatch, capsys):
    # #1254
    doc = tmp_path / "doc.md"
    doc.write_text(f"[a]({server}/flaky) [b]({server}/ok)\n", encoding="utf-8")
    _Handler.flaky_seen.clear()
    slept = []
    monkeypatch.setattr(script.time, "sleep", slept.append)
    seen = {}
    real_run = script.run

    def spy(*args, **kwargs):
        seen["per_host"] = kwargs.get("per_host")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(script, "run", spy)
    assert script.main([str(doc), "--check-local", "--timeout", "5", "--retry-delay", "7", "--per-host", "1"]) == 0
    assert slept == [7.0] and seen["per_host"] == 1
    assert "2 ok" in capsys.readouterr().out


def test_per_host_must_be_at_least_one(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("[a](https://example.org/a)\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        script.main([str(doc), "--per-host", "0"])


def test_fix_moved_rewrites_links_in_the_citing_files_only(tmp_path):
    # #1255
    doc = tmp_path / "doc.md"
    doc.write_text("[a](https://old.example.org/a) and <https://old.example.org/a> and [keep](https://old.example.org/ab)\n"
                   "plain https://old.example.org/a text\n", encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text("[a](https://old.example.org/a)\n", encoding="utf-8")
    untouched = tmp_path / "untouched.md"
    untouched.write_text("[a](https://old.example.org/a)\n", encoding="utf-8")
    report = {"moved": [{"url": "https://old.example.org/a", "detail": "https://new.example.org/a", "files": ["doc.md", "other.md"]}]}

    count, files = script.fix_moved(report, root=tmp_path)

    assert count == 2 and files == [doc, other]
    assert doc.read_text(encoding="utf-8") == ("[a](https://new.example.org/a) and <https://new.example.org/a> and "
                                              "[keep](https://old.example.org/ab)\nplain https://old.example.org/a text\n")
    assert other.read_text(encoding="utf-8") == "[a](https://new.example.org/a)\n"
    assert untouched.read_text(encoding="utf-8") == "[a](https://old.example.org/a)\n"


@pytest.mark.parametrize("new", ["https://example.org/login?next=/a", "https://example.org/404", "https://example.org/error/"])
def test_fix_moved_leaves_a_redirect_to_a_login_or_error_page_alone(tmp_path, new):
    doc = tmp_path / "doc.md"
    doc.write_text("[a](https://old.example.org/a)\n", encoding="utf-8")
    report = {"moved": [{"url": "https://old.example.org/a", "detail": new, "files": ["doc.md"]}]}
    assert script.fix_moved(report, root=tmp_path) == (0, [])
    assert doc.read_text(encoding="utf-8") == "[a](https://old.example.org/a)\n"


def test_main_fix_moved_rewrites_after_reporting(tmp_path, monkeypatch, capsys):
    doc = tmp_path / "doc.md"
    doc.write_text("[a](https://old.example.org/a)\n", encoding="utf-8")
    report = {"checked": 1, "ok": [], "broken": [], "unknown": [], "ignored": [], "stale_ignored": [],
              "moved": [{"url": "https://old.example.org/a", "detail": "https://new.example.org/a", "files": [str(doc)]}]}
    monkeypatch.setattr(script, "run", lambda *a, **k: report)
    assert script.main([str(doc), "--fix-moved"]) == 0
    out = capsys.readouterr().out
    assert "1 moved" in out and "Rewrote 1 moved link(s) in 1 file(s)" in out
    assert doc.read_text(encoding="utf-8") == "[a](https://new.example.org/a)\n"

def test_fix_moved_rewrites_additional_link_formats(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(
        '[Google](https://old.example.org/a "Search")\n'
        '[google]: https://old.example.org/a\n'
        '<a href="https://old.example.org/a">Google</a>\n',
        encoding="utf-8",
    )

    report = {
        "moved": [{
            "url": "https://old.example.org/a",
            "detail": "https://new.example.org/a",
            "files": ["doc.md"],
        }]
    }

    count, files = script.fix_moved(report, root=tmp_path)

    assert count == 1
    assert files == [doc]
    assert doc.read_text(encoding="utf-8") == (
        '[Google](https://new.example.org/a "Search")\n'
        '[google]: https://new.example.org/a\n'
        '<a href="https://new.example.org/a">Google</a>\n'
    )


def test_rebuild_runs_the_explainer_build_only_when_an_explainer_was_rewritten(tmp_path):
    # #1272
    from types import SimpleNamespace
    calls = []

    def runner(command, **kwargs):
        calls.append((command[-1], kwargs["cwd"]))
        return SimpleNamespace(returncode=0)

    (tmp_path / "explainers").mkdir()
    explainer, readme = tmp_path / "explainers" / "x.md", tmp_path / "README.md"
    assert script.rebuild_explainers([readme], root=tmp_path, runner=runner) is None and calls == []
    assert script.rebuild_explainers([readme, explainer], root=tmp_path, runner=runner) == 0
    assert calls == [("scripts/build_explainers.py", tmp_path)]


def test_main_fix_moved_rebuild_reports_and_returns_a_failed_build(tmp_path, monkeypatch, capsys):
    explainers = script.ROOT / "explainers"
    doc = explainers / "tmp-fix-moved-test.md"
    doc.write_text("[a](https://old.example.org/a)\n", encoding="utf-8")
    try:
        report = {"checked": 1, "ok": [], "broken": [], "unknown": [], "ignored": [], "stale_ignored": [],
                  "moved": [{"url": "https://old.example.org/a", "detail": "https://new.example.org/a", "files": [str(doc)]}]}
        monkeypatch.setattr(script, "run", lambda *a, **k: report)
        monkeypatch.setattr(script, "rebuild_explainers", lambda files, **k: 0)
        assert script.main([str(doc), "--fix-moved", "--rebuild"]) == 0
        out = capsys.readouterr().out
        assert "Rewrote 1 moved link(s) in 1 file(s)." in out and "Rebuilt the explainer pages." in out

        doc.write_text("[a](https://old.example.org/a)\n", encoding="utf-8")
        monkeypatch.setattr(script, "rebuild_explainers", lambda files, **k: 3)
        assert script.main([str(doc), "--fix-moved", "--rebuild"]) == 3
        assert "build_explainers.py failed (exit 3)" in capsys.readouterr().out

        doc.write_text("[a](https://old.example.org/a)\n", encoding="utf-8")
        assert script.main([str(doc), "--fix-moved"]) == 0
        assert "an explainer changed, so run `make build-explainers` (or use --rebuild)" in capsys.readouterr().out
    finally:
        doc.unlink(missing_ok=True)


def test_rebuild_without_fix_moved_is_an_error(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("[a](https://example.org/a)\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        script.main([str(doc), "--rebuild"])


def test_main_leaves_the_module_retry_delay_alone_and_passes_the_option_down(tmp_path, monkeypatch):
    # #1287: --retry-delay used to be applied by assigning the module global
    doc = tmp_path / "doc.md"
    doc.write_text("[a](https://example.org/a)\n", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(script, "run", lambda *a, **k: seen.update(k) or {"checked": 0, "ok": [], "moved": [], "broken": [], "unknown": [],
                                                                         "ignored": [], "stale_ignored": []})
    before = script.RETRY_DELAY
    assert script.main([str(doc), "--retry-delay", "7"]) == 0
    assert script.RETRY_DELAY == before and seen["retry_delay"] == 7.0


def test_retry_delay_parameter_reaches_the_sleep_and_overrides_the_constant(server, monkeypatch):
    _Handler.flaky_seen.clear()
    slept = []
    monkeypatch.setattr(script.time, "sleep", slept.append)
    monkeypatch.setattr(script, "RETRY_DELAY", 99.0)
    assert script.check_url(server + "/flaky", timeout=5, retry_delay=3.0) == ("ok", "200")
    assert slept == [3.0]
    assert script._retry_delay(urllib.error.HTTPError("http://x", 503, "x", {}, io.BytesIO())) == 99.0


def test_run_passes_the_retry_delay_to_each_check(monkeypatch):
    seen = []
    monkeypatch.setattr(script, "check_url", lambda url, timeout, retry_delay=None: seen.append(retry_delay) or ("ok", "200"))
    script.run({"https://a.example.org/x": ["a.md"], "https://b.example.org/y": ["a.md"]}, retry_delay=4.5)
    assert seen == [4.5, 4.5]


def _issue_report(unknown):
    return {"checked": 5, "ok": [], "moved": [], "broken": [], "unknown": unknown, "ignored": [], "stale_ignored": []}


def test_the_issue_body_lists_each_unverified_403_link_with_its_files():
    # #1330: the text report had the section, the weekly issue only a count
    report = _issue_report([
        {"url": "https://a.example/x", "detail": "403 (no archive copy)", "files": ["explainers/a.md", "README.md"]},
        {"url": "https://b.example/y", "detail": "403 (archived copy exists)", "files": ["b.md"]},
        {"url": "https://c.example/z", "detail": "503", "files": ["c.md"]},
        {"url": "https://d.example/w", "detail": "403 (no archive copy)", "files": ["d.md"]}])
    body = script.render_issue_body(report)
    assert "Unverified by hand" in body
    assert "- https://a.example/x (in `explainers/a.md`, `README.md`)" in body and "- https://d.example/w (in `d.md`)" in body
    assert "https://b.example/y" not in body and "https://c.example/z" not in body          # archived and other unknowns stay out
    assert "2 of those answered 403 and have no Internet Archive copy" in body


def test_the_issue_body_has_no_unverified_section_when_there_are_none_and_they_never_keep_the_issue_open():
    body = script.render_issue_body(_issue_report([{"url": "https://c.example/z", "detail": "503", "files": ["c.md"]}]))
    assert "Unverified by hand" not in body
    only_unverified = _issue_report([{"url": "https://a.example/x", "detail": "403 (no archive copy)", "files": ["a.md"]}])
    assert script.report_needs_issue(only_unverified) is False                      # listed, not counted as broken


TODAY = script.datetime.date(2026, 11, 19)
UNVERIFIED = ("unknown", "403 (no archive copy)")


def _run_with(monkeypatch, answers, checked, ignore=None):
    monkeypatch.setattr(script, "check_url", lambda url, timeout, **kw: answers[url])
    urls = {url: ["a.md"] for url in answers}
    return script.run(urls, checked=checked, today=TODAY, ignore=ignore)


def test_a_link_checked_by_hand_within_90_days_leaves_the_unverified_list(monkeypatch):
    # #1337: the only way to stop listing a 403 link used to be a permanent ignore entry that stopped any later check
    day = script.datetime.date.fromisoformat
    report = _run_with(monkeypatch, {"https://fresh.example/a": UNVERIFIED, "https://stale.example/b": UNVERIFIED,
                                     "https://never.example/c": UNVERIFIED},
                       {"https://fresh.example/a": (day("2026-11-18"), "opens in a browser"),
                        "https://stale.example/b": (day("2026-08-01"), "opened in August")})
    assert [i["url"] for i in report["checked_by_hand"]] == ["https://fresh.example/a"]
    assert report["checked_by_hand"][0]["checked"] == "2026-11-18" and report["checked_by_hand"][0]["reason"] == "opens in a browser"
    assert sorted(i["url"] for i in report["unknown"]) == ["https://never.example/c", "https://stale.example/b"]   # 110 days: listed again


def test_the_90_day_boundary_is_inclusive_and_a_checked_link_that_breaks_is_still_reported(monkeypatch):
    day = script.datetime.date
    on_the_edge = day(2026, 11, 19) - script.datetime.timedelta(days=90)
    report = _run_with(monkeypatch, {"https://edge.example/a": UNVERIFIED, "https://gone.example/b": ("broken", "404")},
                       {"https://edge.example/a": (on_the_edge, "x"), "https://gone.example/b": (day(2026, 11, 18), "x")})
    assert [i["url"] for i in report["checked_by_hand"]] == ["https://edge.example/a"]
    assert [i["url"] for i in report["broken"]] == ["https://gone.example/b"]              # checking by hand never hides a dead link


def test_only_a_403_with_no_archive_copy_is_moved_and_a_checked_url_nobody_cites_is_stale(monkeypatch):
    day = script.datetime.date(2026, 11, 18)
    report = _run_with(monkeypatch, {"https://other.example/a": ("unknown", "503")},
                       {"https://other.example/a": (day, "x"), "https://uncited.example/z": (day, "was cited once")})
    assert report["checked_by_hand"] == [] and [i["url"] for i in report["unknown"]] == ["https://other.example/a"]
    assert report["stale_ignored"] == [{"url": "checked:https://uncited.example/z", "reason": "was cited once"}]


def test_the_text_report_and_the_issue_body_count_them_without_listing_them_as_unverified(monkeypatch):
    day = script.datetime.date.fromisoformat
    report = _run_with(monkeypatch, {"https://fresh.example/a": UNVERIFIED, "https://never.example/c": UNVERIFIED},
                       {"https://fresh.example/a": (day("2026-11-18"), "opens in a browser")})
    text = script.render(report)
    assert "1 checked by hand." in text and "2026-11-18  https://fresh.example/a  (opens in a browser)" in text
    body = script.render_issue_body(report)
    assert "1 more 403 link(s) with no archive copy were checked by hand within the last 90 days" in body
    assert "- https://never.example/c" in body and "- https://fresh.example/a" not in body
    assert script.report_needs_issue(report) is False


def test_load_checked_list_parses_dated_lines_and_rejects_malformed_ones(tmp_path):
    path = tmp_path / "ignore.txt"
    path.write_text("# comment\nhttps://ignored.example/a needs a login\n"
                    "checked:2026-11-18 https://checked.example/b opens in a browser\n", encoding="utf-8")
    assert script.load_checked_list(path) == {"https://checked.example/b": (script.datetime.date(2026, 11, 18), "opens in a browser")}
    assert script.load_ignore_list(path) == {"https://ignored.example/a": "needs a login"}     # the two readers ignore each other's lines
    for bad in ("checked:yesterday https://x.example/a why", "checked:2026-11-18 not-a-url why", "checked:2026-11-18 https://x.example/a"):
        path.write_text(bad + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="checked:YYYY-MM-DD URL reason"):
            script.load_checked_list(path)
    assert script.load_checked_list(tmp_path / "missing.txt") == {}


def test_main_reads_the_checked_lines_from_the_ignore_file(server, tmp_path, capsys):
    doc = tmp_path / "doc.md"
    doc.write_text(f"[gone]({server}/gone)\n", encoding="utf-8")
    ignore = tmp_path / "ignore.txt"
    ignore.write_text(f"checked:{script.datetime.date.today().isoformat()} {server}/gone opened in a browser\n", encoding="utf-8")
    assert script.main([str(doc), "--timeout", "5", "--check-local", "--ignore-file", str(ignore)]) == 0
    assert "1 broken" in capsys.readouterr().out            # a 404 is not hidden by a checked line


def test_mark_checked_appends_a_valid_line_and_keeps_the_existing_entries(tmp_path):
    ignore = tmp_path / "ignore.txt"
    ignore.write_text("# header\nhttps://ignored.example/a needs a login\n", encoding="utf-8")
    urls = {"https://checked.example/b": ["doc.md"]}
    day = script.datetime.date(2026, 11, 18)

    changed, message = script.mark_checked("https://checked.example/b", "opened in a browser", day, ignore, urls)

    assert changed and "Added" in message and "https://checked.example/b" in message
    assert ignore.read_text(encoding="utf-8") == (
        "# header\nhttps://ignored.example/a needs a login\n"
        "checked:2026-11-18 https://checked.example/b opened in a browser\n"
    )
    assert script.load_checked_list(ignore) == {"https://checked.example/b": (day, "opened in a browser")}
    assert script.load_ignore_list(ignore) == {"https://ignored.example/a": "needs a login"}


def test_mark_checked_replaces_an_earlier_line_for_the_same_url(tmp_path):
    ignore = tmp_path / "ignore.txt"
    ignore.write_text("checked:2026-01-01 https://checked.example/b first look\n"
                      "checked:2026-02-02 https://other.example/c still valid\n", encoding="utf-8")
    urls = {"https://checked.example/b": ["doc.md"]}
    day = script.datetime.date(2026, 11, 18)

    changed, message = script.mark_checked("https://checked.example/b", "opened again", day, ignore, urls)

    assert changed and "Updated" in message
    text = ignore.read_text(encoding="utf-8")
    assert text.count("https://checked.example/b") == 1
    assert "checked:2026-11-18 https://checked.example/b opened again\n" in text
    assert "checked:2026-02-02 https://other.example/c still valid\n" in text
    assert script.load_checked_list(ignore) == {
        "https://checked.example/b": (day, "opened again"),
        "https://other.example/c": (script.datetime.date(2026, 2, 2), "still valid"),
    }


def test_mark_checked_refuses_an_uncited_url_or_an_empty_reason(tmp_path):
    ignore = tmp_path / "ignore.txt"
    ignore.write_text("# header\n", encoding="utf-8")
    urls = {"https://cited.example/a": ["doc.md"]}

    changed, message = script.mark_checked("https://typo.example/z", "why", script.datetime.date(2026, 11, 18), ignore, urls)
    assert not changed and "no tracked file cites" in message
    changed, message = script.mark_checked("https://cited.example/a", "   ", script.datetime.date(2026, 11, 18), ignore, urls)
    assert not changed and "reason is required" in message
    assert ignore.read_text(encoding="utf-8") == "# header\n"       # neither refusal writes anything


def test_main_mark_checked_records_a_link_and_refuses_an_uncited_one(tmp_path, capsys):
    doc = tmp_path / "doc.md"
    doc.write_text("[a](https://cited.example/a)\n", encoding="utf-8")
    ignore = tmp_path / "ignore.txt"

    assert script.main([str(doc), "--ignore-file", str(ignore), "--mark-checked", "https://cited.example/a",
                        "--reason", "opened in a browser", "--date", "2026-11-18"]) == 0
    assert "Added checked entry" in capsys.readouterr().out
    assert script.load_checked_list(ignore) == {
        "https://cited.example/a": (script.datetime.date(2026, 11, 18), "opened in a browser")
    }
    assert script.main([str(doc), "--ignore-file", str(ignore), "--mark-checked", "https://uncited.example/z",
                        "--reason", "why"]) == 1
    assert "no tracked file cites" in capsys.readouterr().out


def _aged(days):
    return TODAY - script.datetime.timedelta(days=days)


def test_checked_links_report_the_day_they_come_back_and_those_within_14_days_are_called_out(monkeypatch):
    # #1348: a link used to return to the unverified list with no warning
    names = {"soon": 80, "edge": 77, "later": 76, "fresh": 1, "last": 90}
    answers = {f"https://{n}.example/a": UNVERIFIED for n in names}
    report = _run_with(monkeypatch, answers, {f"https://{n}.example/a": (_aged(age), "opened") for n, age in names.items()})
    by_url = {i["url"]: i for i in report["checked_by_hand"]}
    assert by_url["https://soon.example/a"]["back_on"] == (_aged(80) + script.datetime.timedelta(days=91)).isoformat()
    assert by_url["https://soon.example/a"]["days_left"] == 11 and by_url["https://last.example/a"]["days_left"] == 1
    assert [i["url"] for i in script.expiring_soon(report)] == ["https://last.example/a", "https://soon.example/a", "https://edge.example/a"]
    assert by_url["https://later.example/a"]["days_left"] == 15 and by_url["https://fresh.example/a"]["days_left"] == 90


def test_the_report_and_the_issue_body_list_the_expiring_links_with_the_command_that_renews_them(monkeypatch):
    report = _run_with(monkeypatch, {"https://soon.example/a": UNVERIFIED, "https://fresh.example/b": UNVERIFIED},
                       {"https://soon.example/a": (_aged(80), "opened"), "https://fresh.example/b": (_aged(1), "opened")})
    text = script.render(report)
    soon = next(i for i in report["checked_by_hand"] if i["url"] == "https://soon.example/a")
    assert "Back in the unverified list within 14 days" in text
    assert f"{soon['back_on']}  https://soon.example/a" in text.split("Back in the unverified list", 1)[1]
    assert "fresh.example/b" not in text.split("Back in the unverified list", 1)[1]
    body = script.render_issue_body(report)
    assert "come back to the unverified list within 14 days" in body and "--mark-checked URL --reason TEXT" in body
    assert f"- https://soon.example/a (back on {soon['back_on']}" in body and "- https://fresh.example/b" not in body
    assert script.report_needs_issue(report) is False                         # a warning, never a reason to open the issue


def test_nothing_is_added_when_no_checked_link_is_near_its_limit(monkeypatch):
    report = _run_with(monkeypatch, {"https://fresh.example/b": UNVERIFIED}, {"https://fresh.example/b": (_aged(1), "opened")})
    assert script.expiring_soon(report) == [] and script.expiring_soon({"ok": []}) == []
    assert "Back in the unverified list" not in script.render(report)
    assert "come back to the unverified list" not in script.render_issue_body(report)


def test_an_ignore_entry_can_carry_an_until_date_and_the_other_loaders_agree_on_it(tmp_path):
    # #1352: a link ignored years ago because a site was down was never looked at again
    path = tmp_path / "ignore.txt"
    path.write_text("https://a.example/x until:2026-12-31 site is down for a rebuild\n"
                    "host:b.example until:2027-03-01 needs a login\n"
                    "https://c.example/y never expires\n"
                    "checked:2026-11-18 https://d.example/z opened\n", encoding="utf-8")
    assert script.load_ignore_list(path) == {"https://a.example/x": "site is down for a rebuild", "host:b.example": "needs a login",
                                            "https://c.example/y": "never expires"}
    assert script.load_ignore_until(path) == {"https://a.example/x": script.datetime.date(2026, 12, 31),
                                              "host:b.example": script.datetime.date(2027, 3, 1)}
    assert script.load_ignore_until(tmp_path / "missing.txt") == {}


def test_a_malformed_until_date_or_an_until_without_a_reason_is_a_clear_error(tmp_path):
    path = tmp_path / "ignore.txt"
    for bad, message in (("https://a.example/x until:soon why", "until:YYYY-MM-DD"),
                         ("https://a.example/x until:2026-12-31", "expected `URL reason`"),
                         ("https://a.example/x until: why", "until:YYYY-MM-DD")):
        path.write_text(bad + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            script.load_ignore_list(path)


def _expired_run(monkeypatch, until):
    monkeypatch.setattr(script, "check_url", lambda url, timeout, **kw: ("ok", "200"))
    urls = {"https://a.example/x": ["a.md"], "https://b.example/y": ["a.md"]}
    ignore = {"https://a.example/x": "site is down", "host:b.example": "login"}
    return script.run(urls, ignore=ignore, ignore_until=until, today=TODAY)


def test_an_entry_whose_last_day_has_passed_stops_hiding_its_link_and_is_reported_expired(monkeypatch):
    report = _expired_run(monkeypatch, {"https://a.example/x": script.datetime.date(2026, 11, 18)})
    assert [i["url"] for i in report["ok"]] == ["https://a.example/x"]                    # requested again
    assert report["expired_ignored"] == [{"url": "https://a.example/x", "reason": "site is down", "until": "2026-11-18"}]
    assert [i["url"] for i in report["ignored"]] == ["https://b.example/y"] and report["stale_ignored"] == []
    assert script.report_needs_issue(report) is True


def test_the_last_day_itself_and_an_entry_with_no_date_still_apply(monkeypatch):
    report = _expired_run(monkeypatch, {"https://a.example/x": TODAY})
    assert report["expired_ignored"] == [] and report["ok"] == []
    assert sorted(i["url"] for i in report["ignored"]) == ["https://a.example/x", "https://b.example/y"]
    assert script.report_needs_issue(report) is False


def test_an_expired_host_entry_checks_every_url_on_that_host(monkeypatch):
    report = _expired_run(monkeypatch, {"host:b.example": script.datetime.date(2026, 1, 1)})
    assert [i["url"] for i in report["ok"]] == ["https://b.example/y"]
    assert report["expired_ignored"][0]["url"] == "host:b.example"


def test_the_report_and_the_issue_body_name_the_expired_entries(monkeypatch):
    report = _expired_run(monkeypatch, {"https://a.example/x": script.datetime.date(2026, 11, 18)})
    assert "Expired ignore entries" in script.render(report) and "2026-11-18  https://a.example/x  (site is down)" in script.render(report)
    body = script.render_issue_body(report)
    assert "1 ignore-list entry has expired" in body and "- https://a.example/x (until 2026-11-18: site is down)" in body
    assert "expired" not in script.render_issue_body(_expired_run(monkeypatch, {}))


IGNORE_TEXT = ("# header comment\n"
               "https://a.example/x until:2026-12-31 site is down for a rebuild\n"
               "host:b.example   until:2027-03-01   needs a login   \n"
               "https://c.example/y never expires\n"
               "checked:2026-11-18 https://d.example/z opened\n"
               "\n")


def _ignore_file(tmp_path, text=IGNORE_TEXT):
    path = tmp_path / "ignore.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_renew_ignore_moves_the_date_and_keeps_the_reason_and_every_other_line(tmp_path):
    # #1361: renewing an until: date meant editing the file by hand
    path = _ignore_file(tmp_path)
    changed, message = script.renew_ignore("https://a.example/x", script.datetime.date(2027, 6, 1), path, today=TODAY)
    assert changed and "Renewed https://a.example/x to 2027-06-01 (was 2026-12-31)" in message
    assert path.read_text(encoding="utf-8") == IGNORE_TEXT.replace("until:2026-12-31", "until:2027-06-01")
    changed, _ = script.renew_ignore("HOST:B.example", script.datetime.date(2028, 1, 1), path, today=TODAY)
    assert changed and "host:b.example   until:2028-01-01   needs a login   " in path.read_text(encoding="utf-8")   # spacing kept
    assert script.load_ignore_until(path) == {"https://a.example/x": script.datetime.date(2027, 6, 1),
                                              "host:b.example": script.datetime.date(2028, 1, 1)}


def test_renew_ignore_refuses_an_unknown_key_an_entry_without_a_date_and_a_past_date(tmp_path):
    path = _ignore_file(tmp_path)
    for key, day, text in (("https://nope.example/q", script.datetime.date(2027, 1, 1), "no ignore entry for https://nope.example/q"),
                           ("https://c.example/y", script.datetime.date(2027, 1, 1), "never expires; nothing renewed"),
                           ("https://a.example/x", script.datetime.date(2026, 11, 18), "is in the past")):
        changed, message = script.renew_ignore(key, day, path, today=TODAY)
        assert not changed and text in message
    assert script.renew_ignore("https://d.example/z", script.datetime.date(2027, 1, 1), path, today=TODAY)[0] is False   # a checked: line is not an ignore
    assert path.read_text(encoding="utf-8") == IGNORE_TEXT                       # nothing was written
    assert script.renew_ignore("https://a.example/x", script.datetime.date(2027, 1, 1), tmp_path / "missing.txt", today=TODAY)[0] is False


def test_the_renew_option_runs_from_the_command_line_and_needs_both_arguments(tmp_path, capsys):
    path = _ignore_file(tmp_path)
    tomorrow = (script.datetime.date.today() + script.datetime.timedelta(days=30)).isoformat()
    assert script.main(["--ignore-file", str(path), "--renew-ignore", "https://a.example/x", "--until", tomorrow]) == 0
    assert f"until:{tomorrow} site is down" in path.read_text(encoding="utf-8") and "Renewed" in capsys.readouterr().out
    assert script.main(["--ignore-file", str(path), "--renew-ignore", "https://c.example/y", "--until", tomorrow]) == 1
    for bad in (["--renew-ignore", "https://a.example/x"], ["--until", tomorrow], ["--renew-ignore", "https://a.example/x", "--until", "soon"]):
        with pytest.raises(SystemExit) as stopped:
            script.main(["--ignore-file", str(path), *bad])
        assert stopped.value.code == 2
