"""Fair Code - dataset representation profiler + cross-domain fairness benchmark harness.

The profiler is the diagnostic counterpart to the project's bias audits: instead
of measuring a model's prediction gap, `faircode` audits a dataset's demographic
representation *before* any model is trained.

    from faircode import profile
    import pandas as pd
    result = profile(pd.read_csv("data.csv"))

The benchmark harness (`faircode.benchmark`, `faircode benchmark` on the CLI)
applies one uniform pipeline - five mitigation strategies x three model families
x six fairness metrics - across every audit.yaml manifest in the repo. See
faircode/MANIFEST_SPEC.md for the manifest schema, faircode/SPEC.md for the
profiler's analysis spec shared with the web engine.
"""

from .compare import compare
from .profiler import profile

__all__ = ["profile", "compare"]
__version__ = "2.3.0"
