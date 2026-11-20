"""check-sources logic without network: a failing / stale probe is reported and drives the exit code."""

from datetime import date

import pandas as pd

from rasyidstat_infer import check_sources as cs


def test_age_status():
    today = date(2026, 3, 10)
    assert cs._age_status(pd.Timestamp("2026-03-09"), today, 4)[0] == cs.OK
    assert cs._age_status(pd.Timestamp("2026-03-01"), today, 4)[0] == cs.WARN
    assert cs._age_status(None, today, 4)[0] == cs.FAIL


def test_failing_probe_sets_exit_code(monkeypatch, capsys):
    def boom(today):
        raise KeyError("column renamed")

    monkeypatch.setattr(cs, "PROBES", {"good": lambda t: (cs.OK, "fine"), "bad": boom})
    results = cs.check_sources(date(2026, 3, 1))
    assert [r[1] for r in results] == [cs.OK, cs.FAIL]
    assert cs.report(results) == 1
    assert "FAILED: bad" in capsys.readouterr().out
    assert cs.report([r for r in results if r[0] == "good"]) == 0
