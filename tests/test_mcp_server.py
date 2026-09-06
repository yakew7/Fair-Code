"""Tests for the MCP server's tool-logic functions (needs the mcp extra).

These exercise the plain `_*_impl` functions directly rather than going
through a live stdio session - the module docstring explains why (keeps the
`mcp` SDK's own API out of the unit of testing). server-registration/schema
smoke coverage is one small test at the bottom.

Run from the repo root:  pytest tests/ -q
"""

import importlib.util

import pytest

pytest.importorskip("mcp", reason="MCP tools need the optional mcp extra")

from faircode.mcp_server import (  # noqa: E402
    _compare_datasets_impl,
    RESULTS_FROZEN_FILES,
    _get_benchmark_results_impl,
    _get_explainer_impl,
    _list_explainers_impl,
    _profile_dataset_impl,
    _proxy_hints_impl,
    build_server,
)

requires_scipy = pytest.mark.skipif(
    importlib.util.find_spec("scipy") is None,
    reason="optional 'proxy' extra not installed",
)

requires_openpyxl = pytest.mark.skipif(
    importlib.util.find_spec("openpyxl") is None,
    reason="optional 'excel' extra not installed",
)


def _write_multi_sheet_xlsx(path, first_col, first_rows):
    import openpyxl

    wb = openpyxl.Workbook()
    first = wb.active
    first.title = "Data"
    first.append([first_col])
    for row in first_rows:
        first.append([row])
    wb.create_sheet("Notes")
    wb.save(path)


def test_profile_dataset_matches_the_shape_profile_returns(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex\n" + "M\n" * 8 + "F\n" * 2, encoding="utf-8")

    result = _profile_dataset_impl(str(path))

    assert set(result) == {"n_rows", "n_cols", "overall_score", "grade",
                          "dimensions_detected", "note", "dimensions",
                          "intersections", "flags", "provenance"}
    assert result["n_rows"] == 10


def test_profile_dataset_exposes_unmeasured_state(tmp_path):
    path = tmp_path / "identifiers.csv"
    path.write_text("id\n" + "\n".join(str(i) for i in range(40)), encoding="utf-8")

    result = _profile_dataset_impl(str(path), include_provenance=False)

    assert result["overall_score"] is None
    assert result["grade"] is None
    assert result["dimensions_detected"] is False
    assert result["note"] == "No demographic columns detected."


def test_profile_dataset_provenance_default_on_and_matches_the_file_hash(tmp_path):
    import hashlib

    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    result = _profile_dataset_impl(str(path))

    expected = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["provenance"]["dataset_hash"] == expected
    assert result["provenance"]["engine"] == "python"


def test_profile_dataset_include_provenance_false_omits_the_block(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    result = _profile_dataset_impl(str(path), include_provenance=False)

    assert "provenance" not in result


def test_profile_dataset_unknown_file_raises_a_clear_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="file not found"):
        _profile_dataset_impl(str(tmp_path / "does-not-exist.csv"))


def test_profile_dataset_rejects_stdin_shorthand():
    # "-" reads real stdin at the CLI, but MCP runs over a stdio transport
    # where stdin IS the JSON-RPC channel - must be rejected, not attempted.
    with pytest.raises(ValueError, match="stdin input"):
        _profile_dataset_impl("-")


def test_compare_datasets_rejects_stdin_shorthand(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    with pytest.raises(ValueError, match="stdin input"):
        _compare_datasets_impl(str(path), "-")


def test_proxy_hints_rejects_stdin_shorthand():
    with pytest.raises(ValueError, match="stdin input"):
        _proxy_hints_impl("-")


def test_profile_dataset_unknown_override_column_raises(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    with pytest.raises(ValueError, match="overrides column"):
        _profile_dataset_impl(str(path), overrides={"not_a_real_column": "sex"})


@requires_openpyxl
def test_profile_dataset_reports_ignored_sheets(tmp_path):
    path = tmp_path / "multi_sheet.xlsx"
    _write_multi_sheet_xlsx(path, "sex", ["M"] * 5 + ["F"] * 5)

    result = _profile_dataset_impl(str(path))

    assert result["sheet_note"] == "read sheet 'Data' - 1 other sheet(s) ignored"


def test_profile_dataset_single_sheet_xlsx_has_no_sheet_note(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    result = _profile_dataset_impl(str(path))

    assert "sheet_note" not in result


def test_profile_dataset_invalid_override_kind_raises(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid kind"):
        _profile_dataset_impl(str(path), overrides={"sex": "not_a_real_kind"})


def test_profile_dataset_cross_with_one_column_raises(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex,race\nM,W\nF,B\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cross expects exactly two"):
        _profile_dataset_impl(str(path), cross=["sex"])


def test_profile_dataset_cross_unknown_column_raises(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex,race\n" + "M,W\nF,B\n" * 25, encoding="utf-8")

    with pytest.raises(ValueError, match="raace"):
        _profile_dataset_impl(str(path), cross=["sex", "raace"])


def test_profile_dataset_cross_same_column_twice_raises(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex,race\n" + "M,W\nF,B\n" * 25, encoding="utf-8")

    with pytest.raises(ValueError, match="cross needs two different columns, got 'sex' twice"):
        _profile_dataset_impl(str(path), cross=["sex", "sex"])


def test_profile_dataset_reference_path_adds_reference_hash_to_provenance(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex\n" + "M\n" * 5 + "F\n" * 5, encoding="utf-8")
    ref = tmp_path / "ref.csv"
    ref.write_text("column,group,share\nsex,M,0.5\nsex,F,0.5\n", encoding="utf-8")

    result = _profile_dataset_impl(str(path), reference_path=str(ref))

    assert "reference_hash" in result["provenance"]
    assert result["dimensions"][0]["reference"] is not None


def test_compare_datasets_matches_the_shape_compare_returns(tmp_path):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\n" + "M\n" * 8 + "F\n" * 2, encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\n" + "M\n" * 5 + "F\n" * 5, encoding="utf-8")

    result = _compare_datasets_impl(str(path_a), str(path_b))

    assert set(result) >= {"a", "b", "score_delta", "dimensions",
                           "added_dimensions", "removed_dimensions", "flags"}
    assert "provenance" in result


def test_compare_datasets_provenance_has_both_dataset_hashes(tmp_path):
    import hashlib

    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nM\n", encoding="utf-8")

    result = _compare_datasets_impl(str(path_a), str(path_b))

    assert result["provenance"]["dataset_hash_a"] == "sha256:" + hashlib.sha256(path_a.read_bytes()).hexdigest()
    assert result["provenance"]["dataset_hash_b"] == "sha256:" + hashlib.sha256(path_b.read_bytes()).hexdigest()


def test_compare_datasets_unknown_override_column_raises(tmp_path):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nM\n", encoding="utf-8")

    with pytest.raises(ValueError, match="overrides column"):
        _compare_datasets_impl(str(path_a), str(path_b), overrides={"nope": "sex"})


@requires_openpyxl
def test_compare_datasets_reports_ignored_sheets_for_both_files(tmp_path):
    path_a = tmp_path / "a.xlsx"
    path_b = tmp_path / "b.xlsx"
    _write_multi_sheet_xlsx(path_a, "sex", ["M"] * 5 + ["F"] * 5)
    _write_multi_sheet_xlsx(path_b, "sex", ["M"] * 5 + ["F"] * 5)

    result = _compare_datasets_impl(str(path_a), str(path_b))

    assert result["sheet_note_a"] == "read sheet 'Data' - 1 other sheet(s) ignored"
    assert result["sheet_note_b"] == "read sheet 'Data' - 1 other sheet(s) ignored"


def test_compare_datasets_proxy_hints_defaults_off(tmp_path):
    path_a = tmp_path / "a.csv"
    path_a.write_text("sex\nM\nF\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("sex\nM\nM\n", encoding="utf-8")

    result = _compare_datasets_impl(str(path_a), str(path_b))

    assert "proxy_hints_a" not in result
    assert "proxy_hints_b" not in result


@requires_scipy
def test_compare_datasets_proxy_hints_attaches_hints_for_both_datasets(tmp_path):
    # occupation is a perfect function of sex in both files -> maximal association.
    rows = ["sex,occupation"] + [
        f"{'male' if i % 2 == 0 else 'female'},{'engineer' if i % 2 == 0 else 'nurse'}"
        for i in range(100)
    ]
    path_a = tmp_path / "a.csv"
    path_a.write_text("\n".join(rows) + "\n", encoding="utf-8")
    path_b = tmp_path / "b.csv"
    path_b.write_text("\n".join(rows) + "\n", encoding="utf-8")

    result = _compare_datasets_impl(str(path_a), str(path_b), proxy_hints=True)

    for key in ("proxy_hints_a", "proxy_hints_b"):
        pair = next(h for h in result[key] if {h["a"], h["b"]} == {"sex", "occupation"})
        assert pair["p_value"] < 0.05


@requires_scipy
def test_proxy_hints_returns_a_dict_with_a_hints_key(tmp_path):
    # occupation is a perfect function of sex -> maximal association.
    rows = ["sex,occupation"] + [
        f"{'male' if i % 2 == 0 else 'female'},{'engineer' if i % 2 == 0 else 'nurse'}"
        for i in range(100)
    ]
    path = tmp_path / "a.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    result = _proxy_hints_impl(str(path))

    assert list(result) == ["hints"]
    pair = next(h for h in result["hints"] if {h["a"], h["b"]} == {"sex", "occupation"})
    assert pair["p_value"] < 0.05


def test_proxy_hints_with_no_significant_pairs_returns_an_empty_list_not_an_error(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    result = _proxy_hints_impl(str(path))

    assert result == {"hints": []}


def test_proxy_hints_runtime_error_propagates_with_a_clean_message(tmp_path, monkeypatch):
    import faircode.mcp_server as mcp_server

    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    def raise_runtime(_df, _dimensions, **_kwargs):
        raise RuntimeError("proxy hints need scipy (install with: pip install faircode[proxy])")

    monkeypatch.setattr(mcp_server, "compute_proxy_hints", raise_runtime)

    with pytest.raises(RuntimeError, match="proxy hints need scipy"):
        _proxy_hints_impl(str(path))


@requires_openpyxl
def test_proxy_hints_reports_ignored_sheets_for_main_path_and_held_out(tmp_path):
    path = tmp_path / "a.xlsx"
    held_path = tmp_path / "held.xlsx"
    _write_multi_sheet_xlsx(path, "sex", ["M"] * 5 + ["F"] * 5)
    _write_multi_sheet_xlsx(held_path, "race", ["A"] * 5 + ["B"] * 5)

    result = _proxy_hints_impl(str(path), held_out_with=[f"{held_path}=race"])

    assert result["sheet_notes"] == [
        "read sheet 'Data' - 1 other sheet(s) ignored",
        "read sheet 'Data' - 1 other sheet(s) ignored",
    ]


@requires_scipy
def test_proxy_hints_held_out_with_flags_a_dropped_column(tmp_path):
    # zip_code is perfectly aligned with race, which has been dropped from
    # the profiled dataset - only visible via held_out_with.
    path = tmp_path / "dropped.csv"
    held_path = tmp_path / "full.csv"
    zip_code = (["111"] * 100 + ["222"] * 100)
    race = (["A"] * 100 + ["B"] * 100)
    path.write_text("zip_code\n" + "\n".join(zip_code), encoding="utf-8")
    held_path.write_text("zip_code,race\n" +
                         "\n".join(f"{z},{r}" for z, r in zip(zip_code, race)),
                         encoding="utf-8")

    result = _proxy_hints_impl(str(path), held_out_with=[f"{held_path}=race"])

    pair = next(h for h in result["hints"] if {h["a"], h["b"]} == {"zip_code", "race"})
    assert pair["p_value"] < 0.05


def test_proxy_hints_held_out_with_malformed_spec_raises_value_error(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("sex\nM\nF\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid held_out_with 'noequalssign'"):
        _proxy_hints_impl(str(path), held_out_with=["noequalssign"])


def test_proxy_hints_held_out_with_column_collision_raises_value_error(tmp_path):
    path = tmp_path / "a.csv"
    held_path = tmp_path / "b.csv"
    path.write_text("sex,race\nM,A\nF,B\n", encoding="utf-8")
    held_path.write_text("race\nX\nY\n", encoding="utf-8")

    with pytest.raises(ValueError, match="column 'race' already exists"):
        _proxy_hints_impl(str(path), held_out_with=[f"{held_path}=race"])


def test_list_explainers_returns_metadata_for_every_published_explainer():
    result = _list_explainers_impl()

    assert result["explainers"]  # the real, current published set - not empty
    slugs = {e["slug"] for e in result["explainers"]}
    assert "proxy-variables" in slugs
    entry = next(e for e in result["explainers"] if e["slug"] == "proxy-variables")
    assert set(entry) == {"slug", "title", "subtitle", "summary", "tags"}
    assert entry["title"] == "Proxy Variables"


def test_list_explainers_filters_by_tag():
    result = _list_explainers_impl(tag="detection")

    assert result["explainers"]
    assert all("detection" in e["tags"] for e in result["explainers"])


def test_list_explainers_unknown_tag_raises():
    with pytest.raises(ValueError, match="no explainer has tag"):
        _list_explainers_impl(tag="not-a-real-tag")


def test_get_explainer_returns_content_and_metadata():
    result = _get_explainer_impl("proxy-variables")

    assert result["slug"] == "proxy-variables"
    assert result["title"] == "Proxy Variables"
    assert "# Explainer: What is a Proxy Variable?" in result["content"]


def test_get_explainer_unknown_slug_raises():
    with pytest.raises(FileNotFoundError, match="no explainer found for slug"):
        _get_explainer_impl("not-a-real-explainer")


@pytest.mark.parametrize("slug", [
    "../README",
    "../../README",
    "../CLAUDE",
    "explainers/../../README",
    "sub/dir",
    "UPPERCASE",
    "has space",
    "trailing.md.md",
])
def test_get_explainer_rejects_path_traversal_and_malformed_slugs(slug):
    # slug is caller-controlled text used to build a filesystem path - a
    # traversal-shaped value used to escape explainers/ and read an
    # arbitrary file elsewhere in the repo (issue #387).
    with pytest.raises(FileNotFoundError, match="no explainer found for slug"):
        _get_explainer_impl(slug)


def test_get_benchmark_results_filters_to_matching_rows():
    # A real, verifiable anchor: COMPAS logistic_regression baseline's race
    # equal_opportunity_diff is cited as 0.926 in explainers/equal-opportunity.md.
    result = _get_benchmark_results_impl(
        audit="compas", model="logistic_regression", strategy="baseline",
        protected_attribute="race", metric="equal_opportunity_diff")

    assert result["total_matches"] == 1
    assert result["truncated"] is False
    row = result["results"][0]
    assert round(row["value"], 3) == 0.926
    assert row["significant"] is True


def test_get_benchmark_results_performance_kind_ignores_protected_attribute_filter():
    # results_performance.csv has no protected_attribute column - a filter
    # naming it should be silently ignored, not raise or return zero rows.
    result = _get_benchmark_results_impl(
        kind="performance", audit="compas", model="logistic_regression",
        protected_attribute="race")

    assert result["total_matches"] > 0
    assert all(row["audit"] == "compas" for row in result["results"])


def test_get_benchmark_results_nan_cells_become_none():
    # results_performance.csv's auc rows have no ci_low/ci_high.
    result = _get_benchmark_results_impl(
        kind="performance", audit="compas", model="logistic_regression",
        strategy="baseline", metric="auc")

    assert result["total_matches"] == 1
    assert result["results"][0]["ci_low"] is None
    assert result["results"][0]["ci_high"] is None


def test_get_benchmark_results_rounds_float_precision():
    # Raw CSV value is -0.06555690919543475 (17 significant digits) - the row
    # cap alone still leaves a large payload once every float carries that
    # many digits it doesn't need for a fairness-metric lookup (#395).
    result = _get_benchmark_results_impl(
        audit="ai_fair_recruitment", model="logistic_regression",
        strategy="baseline", protected_attribute="gender",
        metric="demographic_parity_diff")

    row = result["results"][0]
    assert row["value"] == -0.065557
    for key in ("value", "ci_low", "ci_high", "p_value"):
        decimals = str(float(row[key])).split(".")[-1]
        assert len(decimals) <= 6


def test_get_benchmark_results_no_match_returns_empty_not_an_error():
    result = _get_benchmark_results_impl(audit="not_a_real_audit")

    assert result == {"results": [], "total_matches": 0, "truncated": False}


def test_get_benchmark_results_invalid_kind_raises():
    with pytest.raises(ValueError, match="kind must be one of"):
        _get_benchmark_results_impl(kind="not_a_real_kind")


def test_get_benchmark_results_missing_mirror_names_path_and_safe_recovery(
        tmp_path, monkeypatch):
    missing = tmp_path / "faircode" / "_results_frozen" / "results_fairness.csv"
    monkeypatch.setitem(RESULTS_FROZEN_FILES, "fairness", missing)

    with pytest.raises(FileNotFoundError) as exc_info:
        _get_benchmark_results_impl()

    message = str(exc_info.value)
    assert str(missing) in message
    assert "scripts.freeze_paper_results.mirror_for_mcp()" in message
    assert "may not have been frozen" not in message


@pytest.mark.parametrize("bad_value", [{"x": 1}, ["a", "b"], (1, 2)])
def test_get_benchmark_results_non_scalar_filter_raises_clean_error(bad_value):
    # A dict raised an uncaught NotImplementedError and a list raised a raw
    # pandas ValueError with internal shape-tuple wording - neither is the
    # clean, caught error every other validation failure in this file gives
    # (issue #390).
    with pytest.raises(ValueError, match="audit must be a plain string"):
        _get_benchmark_results_impl(audit=bad_value)


def test_build_server_registers_all_phase_one_and_phase_two_tools():
    import asyncio

    server = build_server()
    tools = asyncio.run(server.list_tools())

    assert {t.name for t in tools} == {
        "profile_dataset", "compare_datasets", "proxy_hints",
        "list_explainers", "get_explainer", "get_benchmark_results",
    }


def test_tool_errors_surface_the_anticipated_message_not_a_generic_one():
    import asyncio

    from mcp.server.mcpserver.exceptions import ToolError

    server = build_server()

    async def call():
        return await server.call_tool("profile_dataset", {"path": "definitely-missing.csv"})

    with pytest.raises(ToolError, match="file not found: definitely-missing.csv"):
        asyncio.run(call())


def test_compare_datasets_tool_error_surfaces_via_call_tool():
    import asyncio

    from mcp.server.mcpserver.exceptions import ToolError

    server = build_server()

    async def call():
        return await server.call_tool(
            "compare_datasets", {"path_a": "definitely-missing.csv", "path_b": "also-missing.csv"})

    with pytest.raises(ToolError, match="file not found: definitely-missing.csv"):
        asyncio.run(call())


def test_proxy_hints_tool_error_surfaces_via_call_tool():
    import asyncio

    from mcp.server.mcpserver.exceptions import ToolError

    server = build_server()

    async def call():
        return await server.call_tool("proxy_hints", {"path": "definitely-missing.csv"})

    with pytest.raises(ToolError, match="file not found: definitely-missing.csv"):
        asyncio.run(call())


def test_get_explainer_tool_error_surfaces_via_call_tool():
    import asyncio

    from mcp.server.mcpserver.exceptions import ToolError

    server = build_server()

    async def call():
        return await server.call_tool("get_explainer", {"slug": "not-a-real-explainer"})

    with pytest.raises(ToolError, match="no explainer found for slug"):
        asyncio.run(call())


def test_get_benchmark_results_tool_error_surfaces_via_call_tool():
    import asyncio

    from mcp.server.mcpserver.exceptions import ToolError

    server = build_server()

    async def call():
        return await server.call_tool("get_benchmark_results", {"kind": "not_a_real_kind"})

    with pytest.raises(ToolError, match="kind must be one of"):
        asyncio.run(call())
