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
        "checked", "ok", "moved", "broken", "unknown", "ignored", "stale_ignored"
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
