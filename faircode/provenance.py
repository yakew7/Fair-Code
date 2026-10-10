"""Provenance metadata for exported profiler results (SPEC section 10).

`profile()` answers "what does this dataset look like". An exported result has
to survive a second question: "what produced these numbers". The same CSV
scores differently under a different `--map`, a different `--min-share`, or a
different reference baseline, and none of that was visible in the export.

The block is attached at the export boundary rather than inside the engines,
so the result shape in SPEC section 6 is unchanged and tests/test_js_parity.py
- which compares the two engine dicts with `==` - needs no edit.

Design notes worth keeping:

* The digest is taken over the **raw file bytes**, not the parsed frame.
  `hashlib.sha256().hexdigest()` and `crypto.subtle.digest('SHA-256', bytes)`
  rendered as lowercase hex produce the identical string, so the CLI and the
  browser agree without sharing code. A canonicalised hash of a parsed frame
  never could.
* When the bytes are not available (stdin, an in-memory frame), the digest is
  `null` with a sibling `_note` saying why. A missing digest must not resemble
  a present one, and must never quietly resemble a match.
* Every field is a function of the inputs, so `--json` stays byte-for-byte
  reproducible across runs.
"""

from __future__ import annotations

import hashlib

from . import __version__

ENGINE = "python"

_CHUNK = 1024 * 1024

# Knobs whose value is a parsed data structure rather than a setting. The
# reference table gets its own digest field, so echoing the whole parsed thing
# into `params` would be noise.
_OPAQUE_PARAMS = ("reference",)


def file_digest(path):
    """Return ("sha256:<hex>", None) for a readable file, or (None, reason).

    Streamed in 1 MiB chunks so a multi-gigabyte CSV is not held in memory
    twice. `hashlib` is stdlib, so this adds no dependency.
    """
    if path in (None, "", "-"):
        return None, "read from stdin; raw bytes were not retained"
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(_CHUNK), b""):
                digest.update(chunk)
    except OSError as exc:
        return None, f"could not read {path} for hashing: {exc}"
    return "sha256:" + digest.hexdigest(), None


def _add_digest(block: dict, field: str, path) -> None:
    """Set `field` on `block` to the digest of `path`, or to None plus a note."""
    sha, note = file_digest(path)
    block[field] = sha
    if note is not None:
        block[field + "_note"] = note


def public_params(resolved: dict) -> dict:
    """The resolved knobs, as actually applied, minus parsed data structures.

    Resolved rather than "the flags the user typed": a reader needs the
    thresholds that were in force, the defaulted ones included, or the numbers
    still cannot be reproduced.
    """
    return {k: v for k, v in sorted(resolved.items()) if k not in _OPAQUE_PARAMS}


def held_out_entries(specs, profiled_columns=None) -> list:
    """Provenance entries for repeated PATH=COLUMN held-out specs (#811).

    One {path, column, sha256} per spec (plus `key` when a join key was given), in the order given; an unreadable path
    (or stdin) gets a null `sha256` and a `sha256_note`, like every other digest.
    `profiled_columns` is forwarded to split_held_out_spec so a colon in a
    column name is resolved the same way as the live parse (#869).
    """
    from .proxy import split_held_out_spec

    entries = []
    for spec in specs or []:
        path, column, key = split_held_out_spec(spec, profiled_columns)
        entry = {"path": path, "column": column}
        if key is not None:
            entry["key"] = key
        _add_digest(entry, "sha256", path)
        entries.append(entry)
    return entries


def sniff_effective_encoding(path: str | None, explicit_encoding: str | None = None) -> str | None:
    """Return explicit encoding or sniffed BOM encoding, or None for plain UTF-8 default.

    When `explicit_encoding` is provided (e.g. from --encoding), it is recorded.
    Otherwise, if the file starts with a known byte-order mark (BOM), the BOM
    encoding is recorded. For the plain UTF-8 default without a BOM, returns
    None so the provenance block keeps its existing shape (§10).
    """
    if explicit_encoding:
        return explicit_encoding
    if not path or path in (None, "", "-"):
        return None
    try:
        from .loaders import sniff_bom_encoding
        with open(path, "rb") as fh:
            return sniff_bom_encoding(fh.read(4))
    except OSError:
        return None


def build(digests=(), params=None, overrides=None, held_out=(), encodings=None) -> dict:
    """Assemble the provenance block attached to an exported result.

    `digests` is a sequence of (field_name, path) pairs, emitted in the order
    given and immediately after the version fields, so the thing that
    identifies the run reads first.

    `encodings` is an optional mapping of field_name to encoding string
    (e.g. {"dataset_hash": "latin-1"} or {"dataset_hash_a": "utf-16"}), placed
    immediately beside the corresponding digest field.

    `held_out` is a sequence of (field_name, specs) or
    (field_name, specs, profiled_columns) triples for the files given to
    `--proxy-hints-with`: each non-empty one is recorded as a list of
    {path, column, sha256} after `overrides`, so the proxy results in the same
    export can be tied to the files that produced them. Omitted when empty, so
    a run without held-out files keeps its existing shape. The optional
    profiled_columns list makes colon-in-column-name resolution match the
    live parse (#869).
    """
    block = {
        "faircode_version": __version__,
        "engine": ENGINE,
    }
    for field, path in digests:
        _add_digest(block, field, path)
        if encodings and field in encodings and encodings[field]:
            enc_key = "encoding" if field == "dataset_hash" else field.replace("dataset_hash_", "encoding_")
            block[enc_key] = encodings[field]
    block["params"] = public_params(params or {})
    block["overrides"] = dict(overrides or {})
    for item in held_out:
        if len(item) == 3:
            field, specs, columns = item
        else:
            field, specs = item
            columns = None
        if specs:
            block[field] = held_out_entries(specs, columns)
    return block
