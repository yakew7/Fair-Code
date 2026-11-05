#!/usr/bin/env python3
"""Reports dead external links in the markdown docs and explainers (#1127).

scripts/check_broken_links.py checks internal links on every run. External links are different: a publisher
or a news site moves a page, and nobody notices until a reader does. They are also slow and flaky to check
(many sites answer a script with 403), so this is a report, never a gate: the weekly workflow runs it and
keeps one issue up to date, and nothing in `make lint` or a pull request depends on it.

    python3 scripts/check_external_links.py                  # explainers/*.md and the top-level docs
    python3 scripts/check_external_links.py --limit 20       # only the first 20 links
    python3 scripts/check_external_links.py --json           # machine-readable, for the workflow
    python3 scripts/check_external_links.py --retry-delay 5 --per-host 1   # slower, gentler on a strict host
    python3 scripts/check_external_links.py --fix-moved       # rewrite permanently moved links in the files that cite them
    python3 scripts/check_external_links.py --fail-on-broken # exit 1 when something is broken (off by default)
    python3 scripts/check_external_links.py --ignore-file F  # use another ignore list (default: the one below)

Each URL is requested with a browser-like user agent and a timeout (HEAD first, then GET when the server does
not allow HEAD). A 404 gets one retry with a fuller browser-like user agent. For a DOI URL blocked with 403,
the DOI handle API is used to distinguish a registered identifier from a missing one. Other 404, 410 and a
name that does not resolve are broken. Everything else (403, 429, 5xx, timeouts, refused connections) is
unknown: it is listed but never counted as broken, because it usually means the site blocks scripts or is down.
A link whose redirect chain starts with a permanent 301 or 308 and ends on a page that answers is moved: the
report lists it with its new address so the document can be updated, and it is never counted as broken (#1196).

A link that is correct but cannot pass an anonymous check (a page behind a login, a deleted account a document
names on purpose) goes in scripts/external-links-ignore.txt: one URL per line, then a reason. The URL is not
requested and does not appear in the broken list, but the report counts it ("N ignored") so the list stays visible.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "Mozilla/5.0 (compatible; FairCodeLinkCheck/1.0; +https://github.com/yakew7/Fair-Code)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 FairCodeLinkCheck/1.0"
)
# a URL may contain balanced parentheses, e.g. https://www.jclinepi.com/article/S0895-4356(15)00001-X/fulltext (#1229)
LINK = re.compile(r"\]\((https?://(?:[^()\s]|\([^()\s]*\))+)\)")
BARE = re.compile(r"<(https?://[^>\s]+)>")
SKIP_HOSTS = {"localhost", "127.0.0.1", "example.com", "www.example.com"}
BROKEN_STATUSES = {404, 410}
MOVED_STATUSES = {301, 308}
RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_DELAY = 2.0          # seconds before the one retry of a transient answer (#1231)
RETRY_AFTER_CAP = 10.0     # a longer Retry-After is not waited for
PER_HOST_REQUESTS = 2      # concurrent requests to one host
IGNORE_FILE = ROOT / "scripts" / "external-links-ignore.txt"


def _ssl_context():
    """The system trust store, or certifi's bundle when the Python build has none (a python.org macOS install
    ships without root certificates until `Install Certificates` is run), so a missing bundle is not mistaken
    for a dead link."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def load_ignore_list(path: Path | None = IGNORE_FILE) -> dict[str, str]:
    """{url or "host:name": reason} from an ignore file: `URL reason` or `host:example.com reason` per line (the second
    skips every URL on that host, #1233), blank lines and `#` comments skipped. A missing file is an empty list; a line
    without a reason is an error, so every exception says why it exists."""
    if path is None or not Path(path).exists():
        return {}
    ignored: dict[str, str] = {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, reason = line.partition(" ")
        if not (re.match(r"https?://\S+$", url) or re.match(r"host:[^\s/:]+$", url)) or not reason.strip():
            raise ValueError(f"{path}:{number}: expected `URL reason` or `host:name reason`, got {line!r}")
        ignored[url.rstrip(".,;") if url.startswith("http") else url.lower()] = reason.strip()
    return ignored


def default_paths():
    return sorted((ROOT / "explainers").glob("*.md")) + sorted(ROOT.glob("*.md"))


def collect_urls(paths, skip_hosts=SKIP_HOSTS) -> dict[str, list[str]]:
    """{url: [files that cite it]} for every external markdown link in `paths`."""
    found: dict[str, list[str]] = {}
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        for url in LINK.findall(text) + BARE.findall(text):
            url = url.rstrip(".,;")
            host = re.match(r"https?://([^/:]+)", url)
            if host and host.group(1).lower() in skip_hosts:
                continue
            files = found.setdefault(url, [])
            name = str(Path(path).relative_to(ROOT)) if Path(path).is_absolute() and ROOT in Path(path).parents else str(path)
            if name not in files:
                files.append(name)
    return found


def check_url(url: str, timeout: float = 15.0) -> tuple[str, str]:
    """(status class, detail) with the class one of 'ok', 'moved', 'broken' or 'unknown'.

    For 'moved' the detail is the address the redirect chain ended on.
    """
    for method in ("HEAD", "GET"):
        try:
            try:
                return _open(url, method, USER_AGENT, timeout)
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise
                # Some sites answer 404 to a non-browser user agent: retry once as a browser, with GET.
                return _open(url, "GET" if method == "HEAD" else method, BROWSER_USER_AGENT, timeout)
        except urllib.error.HTTPError as error:
            result = _classify_http_error(error, url, method, timeout)
            if result is None:
                continue                      # the server does not allow HEAD: try GET
            return result
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            return _classify_network_error(error)
    return "unknown", "no response"


def _retry_delay(error: urllib.error.HTTPError) -> float:
    header = error.headers.get("Retry-After") if error.headers else None
    try:
        return min(max(float(header), 0.0), RETRY_AFTER_CAP) if header is not None else RETRY_DELAY
    except ValueError:
        return RETRY_DELAY


def _open(url: str, method: str, user_agent: str, timeout: float) -> tuple[str, str]:
    """One request; a 429 or 5xx is tried once more after a short wait (Retry-After up to a cap), since those are
    usually a busy server rather than a dead page."""
    try:
        return _open_once(url, method, user_agent, timeout)
    except urllib.error.HTTPError as error:
        if error.code not in RETRY_STATUSES:
            raise
        time.sleep(_retry_delay(error))
        return _open_once(url, method, user_agent, timeout)


def _open_once(url: str, method: str, user_agent: str, timeout: float) -> tuple[str, str]:
    request = urllib.request.Request(url, method=method, headers={"User-Agent": user_agent, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        final_url, status = response.url, str(response.status)
    if final_url != url and _first_redirect_status(request, timeout) in MOVED_STATUSES:
        return "moved", final_url
    return "ok", status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                           # urllib then raises HTTPError with the redirect's own status


def _first_redirect_status(request: urllib.request.Request, timeout: float) -> int | None:
    """The status of the first hop for a URL that redirected, so a temporary 302 or 307 stays 'ok'."""
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_context()), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _classify_http_error(error: urllib.error.HTTPError, url: str, method: str,
                         timeout: float) -> tuple[str, str] | None:
    """The result for an HTTP error status, or None when a HEAD request should be retried as GET."""
    if error.code in BROKEN_STATUSES:
        return "broken", str(error.code)
    if error.code == 403:
        doi = _extract_doi(url)
        if doi:
            return _check_doi(doi, timeout)
        return _check_archive(url, timeout)
    if error.code in (405, 501) and method == "HEAD":
        return None
    return "unknown", str(error.code)


def _classify_network_error(error: OSError) -> tuple[str, str]:
    if isinstance(error, urllib.error.URLError):
        if isinstance(error.reason, socket.gaierror):
            return "broken", "name does not resolve"
        return "unknown", str(error.reason)
    return "unknown", type(error).__name__


def _extract_doi(url: str) -> str | None:
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
    match = re.search(r"10\.\d{4,9}/[^\s?#]+", path, re.IGNORECASE)
    return match.group().rstrip(".,;:)]}") if match else None


def _check_archive(url: str, timeout: float) -> tuple[str, str]:
    """A page that answers scripts with 403 cannot be checked directly. Ask the Internet Archive whether it holds a copy:
    'unknown, 403 (archived copy exists)' says the page existed at some point; 'unknown, 403 (no archive copy)' is the
    list to look at by hand. Neither is counted as broken (#1195). A local address or a failed lookup stays a plain 403."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host in SKIP_HOSTS or host.startswith("127.") or host.endswith(".local"):
        return "unknown", "403"
    endpoint = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
    try:
        with urllib.request.urlopen(urllib.request.Request(endpoint, headers={"Accept": "application/json"}),
                                    timeout=timeout, context=_ssl_context()) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return "unknown", "403"
    closest = (result.get("archived_snapshots") or {}).get("closest") or {}
    return "unknown", "403 (archived copy exists)" if closest.get("available") else "403 (no archive copy)"


def _check_doi(doi: str, timeout: float) -> tuple[str, str]:
    endpoint = f"https://doi.org/api/handles/{urllib.parse.quote(doi, safe='/')}"
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return "broken", "DOI not found"
        return "unknown", f"DOI resolver HTTP {error.code}"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        return "unknown", f"DOI resolver {type(error).__name__}"

    code = result.get("responseCode")
    if code == 1:
        return "ok", "DOI exists"
    if code == 100:
        return "broken", "DOI not found"
    if code == 200:
        return "broken", "DOI has no resolution values"
    return "unknown", f"DOI resolver response {code}"


def run(urls: dict[str, list[str]], limit: int | None = None, workers: int = 8, timeout: float = 15.0,
        ignore: dict[str, str] | None = None, per_host: int | None = None) -> dict:
    ignore = ignore or {}
    per_host = PER_HOST_REQUESTS if per_host is None else per_host

    def ignore_key(url: str) -> str | None:
        """The ignore entry that covers `url`: the exact URL, else its `host:` entry."""
        host = "host:" + (urllib.parse.urlsplit(url).hostname or "").lower()
        return url if url in ignore else host if host in ignore else None

    ignored = [{"url": url, "reason": ignore[ignore_key(url)], "files": urls[url]}
               for url in sorted(urls) if ignore_key(url)]
    used = {ignore_key(url) for url in urls}
    stale_ignored = [{"url": key, "reason": reason} for key, reason in sorted(ignore.items()) if key not in used]
    urls = {url: files for url, files in urls.items() if not ignore_key(url)}
    items = sorted(urls)[:limit] if limit else sorted(urls)
    results = {"ok": [], "moved": [], "broken": [], "unknown": []}
    host_slots: dict[str, threading.Semaphore] = {}
    for url in items:
        host_slots.setdefault(urllib.parse.urlsplit(url).netloc.lower(), threading.Semaphore(per_host))

    def check_with_host_limit(url: str) -> tuple[str, str]:
        with host_slots[urllib.parse.urlsplit(url).netloc.lower()]:
            return check_url(url, timeout)

    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        for url, (kind, detail) in zip(items, pool.map(check_with_host_limit, items)):
            results[kind].append({"url": url, "detail": detail, "files": urls[url]})
    return {"checked": len(items), **{kind: results[kind] for kind in results},
            "ignored": ignored, "stale_ignored": stale_ignored}


def render(report: dict) -> str:
    stale_ignored = report.get("stale_ignored", [])
    lines = [f"Checked {report['checked']} external links: {len(report['ok'])} ok, "
             f"{len(report['broken'])} broken, {len(report['unknown'])} unknown."
             + (f" {len(report['moved'])} moved." if report.get("moved") else "")
             + (f" {len(report['ignored'])} ignored." if report.get("ignored") else "")]
    unverified = [item for item in report["unknown"] if "no archive copy" in item["detail"]]
    sections = (("Broken (404, 410 or a name that does not resolve)", report["broken"]),
                ("Unknown (blocked, rate limited or unreachable; not counted as broken)",
                 [item for item in report["unknown"] if item not in unverified]),
                ("Unverified (403 to scripts and no Internet Archive copy; check by hand, not counted as broken)", unverified))
    for title, items in sections:
        if items:
            lines += ["", title + ":"]
            lines += [f"  {item['detail']:>26}  {item['url']}  ({', '.join(item['files'][:3])})" for item in items]
    if report.get("moved"):
        lines += ["", "Moved (permanent 301 or 308 redirect; update the link, not counted as broken):"]
        lines += [f"  {item['url']}  ->  {item['detail']}  ({', '.join(item['files'][:3])})" for item in report["moved"]]
    if report.get("ignored"):
        lines += ["", "Ignored (listed in scripts/external-links-ignore.txt, not requested):"]
        lines += [f"  {item['url']}  ({item['reason']})" for item in report["ignored"]]
    if stale_ignored:
        lines += ["", f"Stale ignored URLs ({len(stale_ignored)} not found in checked documents):"]
        lines += [f"  {item['url']}  ({item['reason']})" for item in stale_ignored]
    return "\n".join(lines)


def render_issue_body(report: dict) -> str:
    stale_count = len(report.get("stale_ignored", []))
    stale_label = "entry" if stale_count == 1 else "entries"
    lines = [f"The weekly external link check found {len(report['broken'])} broken link(s) among {report['checked']} checked "
             f"({len(report['unknown'])} more could not be verified: blocked, rate limited or unreachable; "
             f"{sum('no archive copy' in item['detail'] for item in report['unknown'])} of those answered 403 and have no "
             f"Internet Archive copy; "
             f"{len(report['ignored'])} listed in `scripts/external-links-ignore.txt` were skipped). "
             f"It also found {stale_count} stale ignore-list {stale_label} with no matching document.", ""]
    for item in report["broken"]:
        lines.append(f"- `{item['detail']}` {item['url']} (in {', '.join('`' + path + '`' for path in item['files'][:5])})")
    lines += ["", "Fix any reported broken links and remove stale ignore-list entries, then run `make build-explainers`. "
              "This issue closes itself on the next weekly run once both are clear. "
              "Reproduce locally with `python3 scripts/check_external_links.py`."]
    return "\n".join(lines) + "\n"


def report_needs_issue(report: dict) -> bool:
    """Keep the weekly issue open while broken links or stale ignores remain."""
    return bool(report["broken"] or report.get("stale_ignored"))


LOGIN_OR_ERROR = re.compile(r"/(?:log-?in|sign-?in|signup|auth|error|404)(?:[/?#]|$)", re.IGNORECASE)


def fix_moved(report: dict, root: Path = ROOT) -> tuple[int, list[Path]]:
    """Rewrite moved links in Markdown and HTML formats."""
    changed: dict[Path, str] = {}
    count = 0

    for item in report.get("moved", []):
        old, new = item["url"], item["detail"]

        if LOGIN_OR_ERROR.search(urllib.parse.urlsplit(new).path):
            continue

        escaped_old = re.escape(old)

        for name in item["files"]:
            path = Path(name) if Path(name).is_absolute() else root / name
            text = changed.get(path)
            if text is None:
                text = path.read_text(encoding="utf-8")

            fixed = re.sub(
                rf"(\]\(\s*){escaped_old}(?=\s*(?:\"[^\"]*\"|'[^']*'|\([^)]*\))?\s*\))",
                lambda m: m.group(1) + new,
                text,
            )

            fixed = re.sub(
                rf"(?m)^(\s*\[[^\]]+\]:\s*<?){escaped_old}(?=>?(?:\s+.*)?$)",
                lambda m: m.group(1) + new,
                fixed,
            )

            fixed = re.sub(
                rf"""(?i)(\bhref\s*=\s*)(["']){escaped_old}\2""",
                lambda m: m.group(1) + m.group(2) + new + m.group(2),
                fixed,
            )

            fixed = fixed.replace(f"<{old}>", f"<{new}>")

            if fixed != text:
                changed[path] = fixed
                count += 1

    for path, text in changed.items():
        path.write_text(text, encoding="utf-8")

    return count, sorted(changed)

def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def main(argv=None) -> int:
    global RETRY_DELAY
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="*", type=Path, help="markdown files to check (default: explainers/*.md and the top-level docs)")
    parser.add_argument("--limit", type=int, help="check at most this many links")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--retry-delay", type=float, default=RETRY_DELAY, metavar="SECONDS",
                        help=f"wait before the one retry of a 429 or 5xx answer (default {RETRY_DELAY:g}; a Retry-After header wins, up to {RETRY_AFTER_CAP:g})")
    parser.add_argument("--per-host", type=_positive_int, default=PER_HOST_REQUESTS, metavar="N",
                        help=f"at most N concurrent requests to one host (default {PER_HOST_REQUESTS})")
    parser.add_argument("--check-local", action="store_true", help="also check localhost and example.com links (for tests)")
    parser.add_argument("--ignore-file", type=Path, default=IGNORE_FILE, help="URL-and-reason list of links not to check")
    parser.add_argument("--fix-moved", action="store_true",
                        help="rewrite permanently moved links to their new address in the files that cite them")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--fail-on-broken", action="store_true", help="exit 1 when a link is broken (off by default)")
    args = parser.parse_args(argv)
    RETRY_DELAY = args.retry_delay
    report = run(collect_urls(args.paths or default_paths(), () if args.check_local else SKIP_HOSTS), args.limit,
                 timeout=args.timeout, ignore=load_ignore_list(args.ignore_file), per_host=args.per_host)
    print(json.dumps(report, indent=2) if args.json else render(report))
    if args.fix_moved:
        count, files = fix_moved(report)
        print(f"Rewrote {count} moved link(s) in {len(files)} file(s)"
              + ("; run `make build-explainers` if an explainer changed." if files else "."), file=sys.stderr if args.json else sys.stdout)
    return 1 if args.fail_on_broken and report["broken"] else 0


if __name__ == "__main__":
    sys.exit(main())
