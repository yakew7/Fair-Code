"""Tests for the export provenance block (SPEC section 10)."""

import hashlib
import json

import pytest

from faircode import __version__
from faircode.cli import main
from faircode.provenance import build, file_digest, public_params
from faircode.report import to_json

ROWS = "gender,region,age\nmale,north,34\nfemale,south,51\nfemale,north,22\n"


def sha_of(path) -> str:
    """Expected digest, read back off disk.

    Deliberately not sha256(ROWS.encode()): a text-mode write translates "\\n"
    to "\\r\\n" on Windows, so the bytes on disk are not the bytes of the
    literal. The digest identifies the file as stored, which is the property
    the block claims - and the reason a CRLF checkout of one logical CSV
    digests differently from an LF one.
    """
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def dataset(tmp_path):
    path = tmp_path / "people.csv"
    path.write_text(ROWS, encoding="utf-8")
    return path


# -- the digest itself -------------------------------------------------------

def test_digest_is_over_raw_file_bytes(dataset):
    """The browser hashes the uploaded bytes; the CLI hashes the same thing, or
    a web report and a CLI report of one file can never be recognised as the
    same measurement. Lowercase hex is what both crypto.subtle.digest and
    hashlib.hexdigest render, so the two sides need no shared code."""
    sha, note = file_digest(str(dataset))
    assert sha == sha_of(dataset)
    assert note is None


def test_digest_changes_with_one_byte(dataset, tmp_path):
    other = tmp_path / "people2.csv"
    other.write_text(ROWS.replace("north", "NORTH", 1), encoding="utf-8")
    assert file_digest(str(dataset))[0] != file_digest(str(other))[0]


def test_missing_digest_is_null_with_a_reason_not_a_lookalike():
    """An unavailable digest must not resemble a present one, and must say why."""
    block = build([("dataset_hash", "-")])
    assert block["dataset_hash"] is None
    assert "stdin" in block["dataset_hash_note"]

    unreadable = build([("dataset_hash", "no/such/file.csv")])
    assert unreadable["dataset_hash"] is None
    assert "no/such/file.csv" in unreadable["dataset_hash_note"]


def test_note_is_absent_when_the_digest_is_present(dataset):
    assert "dataset_hash_note" not in build([("dataset_hash", str(dataset))])


def test_digest_reads_before_the_knobs(dataset):
    """The thing that identifies the run should be the first thing read."""
    keys = list(build([("dataset_hash", str(dataset))], {"min_share": 0.05}, {}))
    assert keys.index("dataset_hash") < keys.index("params")


# -- the block ---------------------------------------------------------------

def test_params_are_the_resolved_ones_not_the_flags_typed():
    resolved = {"min_share": 0.2, "missing_flag": 0.05, "reference": {"sex": {"m": 0.5}}}
    params = public_params(resolved)
    assert params["min_share"] == 0.2
    assert params["missing_flag"] == 0.05
    # the parsed reference table gets its own digest field, not an echo here
    assert "reference" not in params


def test_block_is_a_pure_function_of_its_inputs():
    """Nothing wall-clock is recorded, so --json output stays byte-for-byte
    reproducible across runs - which matters in a repo that pins numbers."""
    assert build([], {"min_share": 0.05}, {"a": "sex"}) == \
           build([], {"min_share": 0.05}, {"a": "sex"})


def test_to_json_attaches_without_mutating_or_overwriting():
    result = {"n_rows": 3, "flags": []}
    payload = json.loads(to_json(result, provenance=build()))
    assert payload["n_rows"] == 3
    assert payload["flags"] == []
    assert payload["provenance"]["faircode_version"] == __version__
    assert "provenance" not in result  # the caller still renders terminal/HTML


def test_to_json_unchanged_when_no_provenance_passed():
    result = {"n_rows": 3}
    assert json.loads(to_json(result)) == result


# -- end to end through the CLI ---------------------------------------------

def test_profile_json_carries_dataset_identity(dataset, capsys):
    assert main(["profile", str(dataset), "--json"]) == 0
    prov = json.loads(capsys.readouterr().out)["provenance"]
    assert prov["faircode_version"] == __version__
    assert prov["engine"] == "python"
    assert prov["dataset_hash"] == sha_of(dataset)


def test_engine_result_keys_are_untouched(dataset, capsys):
    """Additive: the block is a new sibling key, nothing existing moves."""
    assert main(["profile", str(dataset), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"n_rows", "n_cols", "overall_score", "grade",
                           "dimensions_detected", "note", "dimensions",
                           "intersections", "flags", "provenance"}


def test_overrides_and_thresholds_are_recorded(dataset, capsys):
    """A --map or a moved threshold changes the numbers. Before this block the
    export gave a reader no way to see that it had happened."""
    assert main(["profile", str(dataset), "--json",
                 "--map", "region=geography", "--min-share", "0.4"]) == 0
    prov = json.loads(capsys.readouterr().out)["provenance"]
    assert prov["overrides"] == {"region": "geography"}
    assert prov["params"]["min_share"] == 0.4
    # defaulted knobs are recorded too, or the run still cannot be reproduced
    assert prov["params"]["missing_flag"] == 0.05


def test_reference_baseline_gets_its_own_digest(dataset, tmp_path, capsys):
    baseline = tmp_path / "census.csv"
    baseline.write_text("column,group,share\ngender,male,0.49\ngender,female,0.51\n",
                        encoding="utf-8")
    assert main(["profile", str(dataset), "--json", "--reference", str(baseline)]) == 0
    prov = json.loads(capsys.readouterr().out)["provenance"]
    assert prov["dataset_hash"] == sha_of(dataset)
    assert prov["reference_hash"] == sha_of(baseline)


def test_reference_hash_absent_when_no_baseline_given(dataset, capsys):
    assert main(["profile", str(dataset), "--json"]) == 0
    assert "reference_hash" not in json.loads(capsys.readouterr().out)["provenance"]


def test_compare_json_records_both_sides(dataset, tmp_path, capsys):
    other = tmp_path / "later.csv"
    other.write_text(ROWS + "male,south,60\n", encoding="utf-8")
    assert main(["compare", str(dataset), str(other), "--json"]) == 0
    prov = json.loads(capsys.readouterr().out)["provenance"]
    assert prov["dataset_hash_a"] == sha_of(dataset)
    assert prov["dataset_hash_b"] == sha_of(other)
    assert prov["dataset_hash_a"] != prov["dataset_hash_b"]


def test_stdin_profile_still_exports_a_block(dataset, capsys, monkeypatch):
    """Reading from stdin must not drop the version and params too."""
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(ROWS))
    assert main(["profile", "-", "--json"]) == 0
    prov = json.loads(capsys.readouterr().out)["provenance"]
    assert prov["dataset_hash"] is None
    assert "stdin" in prov["dataset_hash_note"]
    assert prov["faircode_version"] == __version__
    assert prov["params"]["min_share"] == 0.05


def test_no_provenance_flag_restores_the_old_shape(dataset, capsys):
    assert main(["profile", str(dataset), "--json", "--no-provenance"]) == 0
    assert "provenance" not in json.loads(capsys.readouterr().out)


def test_terminal_output_is_untouched(dataset, capsys):
    assert main(["profile", str(dataset)]) == 0
    assert "provenance" not in capsys.readouterr().out.lower()
