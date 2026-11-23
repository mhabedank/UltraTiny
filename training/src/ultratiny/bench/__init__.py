"""Benchmark and KPI report (specs/007-benchmark-kpi-bericht).

Modules:
    suite    suite loading with SHA-256 pin checks (research R3, R4)
    scoring  visible-answer scoring and KPI aggregation (R5)
    subject  model adapters: answer() and bit costs (R2)
    lm       S1 bits per character and S2 recall (R6, R7)
    pc       PC measurement run and --check (R11)
    board    board measurement over the serial console (R8)
    report   comparison report, verdicts, Markdown and HTML (R9, R10)
    demo     demo runner (FR-022)
"""

TOOL_VERSION = "bench 1"
RESULT_FORMAT = 1
