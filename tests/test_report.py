import pytest

# Adjust the import path to match your package structure (e.g., faircode.report)
from faircode.report import compare_to_html, compare_to_terminal, to_html, to_terminal


@pytest.fixture
def mock_profile_result():
    return {
        "n_rows": 1250,
        "n_cols": 8,
        "overall_score": 88,
        "grade": "B+",
        "dimensions": [
            {
                "name": "Gender",
                "kind": "Demographic",
                "dimension_score": 85,
                "under_represented": ["Non-binary"],
                "n_groups": 2,
                "imbalance_ratio": 1.6,
                "missing_pct": 0.02,
                "skewness": 0.3,
                "groups": [
                    {
                        "label": "Female",
                        "share": 0.45,
                        "count": 562,
                        "ci_low": 0.42,
                        "ci_high": 0.48,
                    }
                ],
            }
        ],
        "flags": ["Gender under-representation detected"],
    }


@pytest.fixture
def mock_compare_result():
    return {
        "score_delta": -5,
        "a": {"name": "Dataset A", "overall_score": 90, "n_rows": 1000, "grade": "A"},
        "b": {"name": "Dataset B", "overall_score": 85, "n_rows": 1200, "grade": "B"},
        "added_dimensions": ["NewDim"],
        "removed_dimensions": ["OldDim"],
        "flags": ["High drift in Gender"],
        "dimensions": [
            {
                "name": "Gender",
                "kind": "Demographic",
                "drift_level": "significant",
                "psi": 0.125,
                "tvd": 0.082,
                "dimension_score_a": 92,
                "dimension_score_b": 85,
                "dimension_score_delta": -7,
                "groups": [
                    {
                        "label": "Female",
                        "status": "shifted",
                        "share_a": 0.50,
                        "share_b": 0.40,
                        "share_delta": -0.10,
                    }
                ],
            }
        ],
    }


def test_to_html_smoke(mock_profile_result):
    """Smoke test for profile report rendering."""
    html_out = to_html(mock_profile_result)

    assert html_out.startswith("<!DOCTYPE html>")
    assert "</html>" in html_out
    assert "Dataset Representation Profile" in html_out


def test_to_html_renders_key_figures(mock_profile_result):
    """Verify raw calculated metrics appear in the rendered HTML."""
    html_out = to_html(mock_profile_result)

    assert "1,250" in html_out
    assert "88/100" in html_out
    assert "B+" in html_out
    assert "Gender" in html_out
    assert "imbalance 1.6x" in html_out
    assert "missing 2.0%" in html_out
    assert "skew +0.30" in html_out


def test_to_html_renders_proxy_hints(mock_profile_result):
    mock_profile_result["proxy_hints"] = [
        {"a": "sex", "b": "region", "p_value": 1.64e-22, "cramers_v": 0.98}
    ]

    html_out = to_html(mock_profile_result)

    assert "Proxy Hints" in html_out
    assert "sex" in html_out and "region" in html_out
    assert "0.98" in html_out


def test_to_html_omits_proxy_hints_section_when_absent(mock_profile_result):
    html_out = to_html(mock_profile_result)

    assert "Proxy Hints" not in html_out


def test_to_html_renders_reference_baseline_section(mock_profile_result):
    mock_profile_result["dimensions"][0]["reference"] = {
        "deviation": 0.2,
        "groups": [
            {"label": "Female", "expected": 0.5, "actual": 0.45, "delta": -0.05},
        ],
    }

    html_out = to_html(mock_profile_result)

    assert "Reference" in html_out
    assert "deviation 20.0%" in html_out
    assert "50.0%" in html_out and "45.0%" in html_out
    assert "-5.0 pp" in html_out


def test_to_html_omits_reference_section_when_absent(mock_profile_result):
    html_out = to_html(mock_profile_result)

    assert '<div class="reference">' not in html_out


def test_compare_to_html_smoke(mock_compare_result):
    """Smoke test for comparison drift report rendering."""
    html_out = compare_to_html(mock_compare_result)

    assert html_out.startswith("<!DOCTYPE html>")
    assert "</html>" in html_out
    assert "Representation Drift" in html_out


def test_compare_to_html_renders_key_figures(mock_compare_result):
    """Verify key drift metrics appear in the comparison report."""
    html_out = compare_to_html(mock_compare_result)

    assert "PSI" in html_out
    assert "0.125" in html_out
    assert "0.082" in html_out
    assert "significant" in html_out
    assert "Dataset A" in html_out
    assert "Dataset B" in html_out


def test_compare_to_html_styles_all_three_drift_levels(mock_compare_result):
    # Only .drift-badge.significant was styled; "moderate" and "none" fell
    # back to the flat grey base style, indistinguishable from each other
    # in the exported/CLI --html report (closes #322).
    html_out = compare_to_html(mock_compare_result)

    assert ".drift-badge.none" in html_out
    assert ".drift-badge.moderate" in html_out
    assert ".drift-badge.significant" in html_out


def test_compare_to_html_renders_added_removed_dimensions(mock_compare_result):
    """Mirrors test_compare_to_terminal_renders_added_removed_dimensions for
    the HTML branch, which had no equivalent coverage (#302)."""
    html_out = compare_to_html(mock_compare_result)

    assert "Only in B" in html_out and "NewDim" in html_out
    assert "Only in A" in html_out and "OldDim" in html_out


def test_compare_to_html_renders_appeared_disappeared_groups(mock_compare_result):
    """Mirrors compare_to_terminal's appeared/disappeared coverage for the
    HTML branch's class="gone"/"new" row styling and status tag (#302)."""
    mock_compare_result["dimensions"][0]["groups"] = [
        {"label": "Female", "status": "shifted", "share_a": 0.50, "share_b": 0.40, "share_delta": -0.10},
        {"label": "Non-binary", "status": "appeared", "share_a": 0.0, "share_b": 0.05, "share_delta": 0.05},
        {"label": "Prefer not to say", "status": "disappeared", "share_a": 0.03, "share_b": 0.0, "share_delta": -0.03},
    ]

    html_out = compare_to_html(mock_compare_result)

    assert 'class="drift-row new"' in html_out
    assert 'class="drift-row gone"' in html_out
    assert '<span class="tag">appeared</span>' in html_out
    assert '<span class="tag">disappeared</span>' in html_out
    assert "Non-binary" in html_out
    assert "Prefer not to say" in html_out


def test_to_terminal_smoke(mock_profile_result):
    """Smoke test for the default (no --json/--html) profile report."""
    out = to_terminal(mock_profile_result)

    assert out.startswith("=" * 20)
    assert "FAIR CODE - DATASET REPRESENTATION PROFILE" in out


def test_to_terminal_renders_key_figures(mock_profile_result):
    out = to_terminal(mock_profile_result)

    assert "1,250" in out
    assert "88/100" in out
    assert "B+" in out
    assert "Gender" in out
    assert "Female" in out
    assert "<- under-represented" not in out  # Female isn't in under_represented


def test_to_terminal_marks_under_represented_group(mock_profile_result):
    mock_profile_result["dimensions"][0]["under_represented"] = ["Female"]

    out = to_terminal(mock_profile_result)

    assert "Female" in out
    assert "<- under-represented" in out


def test_to_terminal_truncates_a_long_group_label_and_keeps_alignment(mock_profile_result):
    label = "Not Hispanic or Latino"  # 22 chars, over the [:18] truncation
    mock_profile_result["dimensions"][0]["groups"][0]["label"] = label

    out = to_terminal(mock_profile_result)

    assert label[:18] in out
    assert label not in out  # the full, untruncated label must not appear
    truncated_line = next(line for line in out.splitlines() if label[:18] in line)
    # The truncated label pads to a fixed 18-char column, so the share
    # percentage that follows still lands where every other row's does.
    assert " 45.0%" in truncated_line


def test_to_terminal_truncates_a_long_reference_group_label(mock_profile_result):
    ref_label = "Some Long Reference Group Name"  # 31 chars, over [:16]
    mock_profile_result["dimensions"][0]["reference"] = {
        "deviation": 0.05,
        "groups": [
            {"label": ref_label, "expected": 0.5, "actual": 0.45, "delta": -0.05},
        ],
    }

    out = to_terminal(mock_profile_result)

    assert ref_label[:16] in out
    assert ref_label not in out


def test_to_terminal_renders_flags_section(mock_profile_result):
    out = to_terminal(mock_profile_result)

    assert "FLAGS" in out
    assert "Gender under-representation detected" in out


def test_to_terminal_renders_proxy_hints(mock_profile_result):
    mock_profile_result["proxy_hints"] = [
        {"a": "sex", "b": "region", "p_value": 1.64e-22, "cramers_v": 0.98}
    ]

    out = to_terminal(mock_profile_result)

    assert "PROXY HINTS" in out
    assert "sex" in out and "region" in out


def test_to_terminal_no_dimensions_detected():
    result = {
        "n_rows": 10, "n_cols": 2, "overall_score": None, "grade": None,
        "dimensions_detected": False, "note": "No demographic columns detected.",
        "dimensions": [], "flags": [],
    }

    out = to_terminal(result)
    html_out = to_html(result)

    assert "No demographic columns detected." in out
    assert "Grade F" not in out
    assert "0/100" not in out
    assert "Not measured" in html_out
    assert "None/100" not in html_out


def test_compare_to_terminal_smoke(mock_compare_result):
    """Smoke test for the default (no --json/--html) compare report."""
    out = compare_to_terminal(mock_compare_result)

    assert out.startswith("=" * 20)
    assert "FAIR CODE - REPRESENTATION DRIFT" in out


def test_compare_to_terminal_renders_key_figures(mock_compare_result):
    out = compare_to_terminal(mock_compare_result)

    assert "Dataset A" in out
    assert "Dataset B" in out
    assert "PSI 0.125" in out
    assert "significant drift" in out
    assert "TVD 0.082" in out


def test_compare_to_terminal_renders_added_removed_dimensions(mock_compare_result):
    out = compare_to_terminal(mock_compare_result)

    assert "Only in B: NewDim" in out
    assert "Only in A: OldDim" in out


def test_compare_to_terminal_renders_drift_flags(mock_compare_result):
    out = compare_to_terminal(mock_compare_result)

    assert "DRIFT FLAGS" in out
    assert "High drift in Gender" in out


def test_compare_to_terminal_no_shared_dimensions():
    out = compare_to_terminal({
        "score_delta": 0,
        "a": {"name": "A", "overall_score": 100, "n_rows": 10, "grade": "A"},
        "b": {"name": "B", "overall_score": 100, "n_rows": 10, "grade": "A"},
        "added_dimensions": [], "removed_dimensions": [], "flags": [], "dimensions": [],
    })

    assert "No shared demographic dimensions to compare." in out


def test_compare_reports_unmeasured_score_without_formatting_none():
    result = {
        "score_delta": None,
        "a": {"name": "A", "overall_score": 100, "n_rows": 10, "grade": "A"},
        "b": {"name": "B", "overall_score": None, "n_rows": 10, "grade": None},
        "added_dimensions": [], "removed_dimensions": [], "flags": [], "dimensions": [],
    }

    terminal_out = compare_to_terminal(result)
    html_out = compare_to_html(result)

    assert "score not measured" in terminal_out
    assert "Overall score change: not available" in terminal_out
    assert "score change not available" in html_out
    assert "None" not in html_out
