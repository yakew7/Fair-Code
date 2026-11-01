import importlib
import sys
from pathlib import Path

check = importlib.import_module("scripts.check_explainer_count")


def _site(root: Path, slugs, readme_slugs, llms_slugs) -> Path:
    (root / "explainers").mkdir()
    for slug in slugs:
        (root / "explainers" / f"{slug}.md").write_text("# x\n", encoding="utf-8")
    (root / "README.md").write_text(
        "".join(f"- [{s}](explainers/{s}.md)\n" for s in readme_slugs), encoding="utf-8"
    )
    (root / "llms.txt").write_text(
        "".join(f"- [{s}](https://www.thefaircode.xyz/explainers/{s}.html)\n" for s in llms_slugs),
        encoding="utf-8",
    )
    return root


def test_every_explainer_listed_passes(tmp_path):
    root = _site(tmp_path, ["a", "b"], ["a", "b"], ["b", "a"])
    assert check.missing_listings(root) == []


def test_unlisted_explainer_is_named_per_file(tmp_path):
    root = _site(tmp_path, ["a", "b", "c"], ["a"], ["a", "b"])
    assert check.missing_listings(root) == [("README.md", ["b", "c"]), ("llms.txt", ["c"])]


def test_readme_accepts_html_links(tmp_path):
    root = _site(tmp_path, ["a"], [], ["a"])
    (root / "README.md").write_text("[a](explainers/a.html)\n", encoding="utf-8")
    assert check.missing_listings(root) == []


def test_repository_lists_every_explainer():
    assert check.missing_listings() == []


def test_main_fails_and_names_the_missing_slug(tmp_path, monkeypatch, capsys):
    root = _site(tmp_path, ["a", "new-one"], ["a"], ["a", "new-one"])
    monkeypatch.setattr(check, "ROOT", root)
    monkeypatch.setattr(check, "EXPLAINERS_DIR", root / "explainers")
    monkeypatch.setattr(check, "CHECKS", [])
    assert check.main() == 1
    assert "README.md: does not list new-one" in capsys.readouterr().err


def _count_site(root: Path, count: int = 2) -> Path:
    root.mkdir()
    explainers = root / "explainers"
    explainers.mkdir()
    for slug in ("one", "two"):
        (explainers / f"{slug}.md").write_text("# x\n", encoding="utf-8")
    (root / "README.md").write_text(
        f"Show all {count} explainers\n"
        f"Explainers Published | {count}\n"
        f"{count} short, plain-language write-ups\n"
        "- [one](explainers/one.md)\n"
        "- [two](explainers/two.html)\n",
        encoding="utf-8",
    )
    (root / "CONTRIBUTORS.md").write_text(
        f"the bulk of the {count} explainers\n", encoding="utf-8"
    )
    (root / "METRICS.md").write_text(
        f"Explainers-{count}-blueviolet\n| Explainers | {count} |\n",
        encoding="utf-8",
    )
    (root / "ROADMAP.md").write_text(
        f"{count} explainers published\n"
        "| Stars | Contributors | Forks | Watching | Social Reach | Countries | Audits | Explainers | CI |\n"
        "|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|\n"
        f"| 54 | 58 | 67 | 8 | 30K+ | 20 | 7 | {count} | ok |\n",
        encoding="utf-8",
    )
    (root / "llms.txt").write_text(
        "- /explainers/one.html\n- /explainers/two.html\n", encoding="utf-8"
    )
    return root


def _run_main(root: Path, monkeypatch, args=()):
    monkeypatch.setattr(check, "ROOT", root)
    monkeypatch.setattr(check, "EXPLAINERS_DIR", root / "explainers")
    monkeypatch.setattr(sys, "argv", ["check_explainer_count.py", *args])
    return check.main()


def test_main_passes_when_all_count_patterns_and_listings_match(
    tmp_path, monkeypatch, capsys
):
    root = _count_site(tmp_path / "site")

    assert _run_main(root, monkeypatch) == 0

    assert "all 8 explainer-count mentions match" in capsys.readouterr().out


def test_main_reports_stale_counts_and_both_missing_listings(
    tmp_path, monkeypatch, capsys
):
    root = _count_site(tmp_path / "site", count=1)
    (root / "README.md").write_text("Show all 1 explainers\n", encoding="utf-8")
    (root / "llms.txt").write_text("", encoding="utf-8")

    assert _run_main(root, monkeypatch) == 1

    captured = capsys.readouterr()
    assert "says 1 explainers, but explainers/*.md has 2" in captured.err
    assert "README.md: does not list one, two" in captured.err
    assert "llms.txt: does not list one, two" in captured.err
    assert "--fix" in captured.err


def test_main_fix_rewrites_only_count_mentions(tmp_path, monkeypatch, capsys):
    root = _count_site(tmp_path / "site", count=1)
    before = {
        name: (root / name).read_text(encoding="utf-8")
        for name in ("README.md", "CONTRIBUTORS.md", "METRICS.md", "ROADMAP.md")
    }

    assert _run_main(root, monkeypatch, ["--fix"]) == 0

    captured = capsys.readouterr()
    assert "Corrected 8 explainer-count mention(s)" in captured.out
    assert "README.md: 1 -> 2" in captured.out
    for name, text in before.items():
        fixed = (root / name).read_text(encoding="utf-8")
        assert fixed == text.replace("1", "2")
    assert "up to date" not in captured.out


def test_main_fix_reports_missing_pattern_and_listing_without_suggesting_fix(
    tmp_path, monkeypatch, capsys
):
    root = _count_site(tmp_path / "site")
    (root / "METRICS.md").write_text("badge only\n", encoding="utf-8")
    (root / "README.md").write_text("Show all 2 explainers\n", encoding="utf-8")

    assert _run_main(root, monkeypatch, ["--fix"]) == 1

    captured = capsys.readouterr()
    assert "expected pattern not found" in captured.err
    assert "README.md: does not list one, two" in captured.err
    assert "Run 'python3 scripts/check_explainer_count.py --fix'" not in captured.err
