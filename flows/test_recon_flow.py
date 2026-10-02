"""Tests for the Prefect orchestration. Run:  pytest flows/ -q"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from prefect.testing.utilities import prefect_test_harness

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "flows"))

import recon_flow  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def prefect_env():
    with prefect_test_harness():
        yield


def test_full_pipeline_runs_and_all_dbt_tests_pass():
    result = recon_flow.recon_pipeline(target="dev")
    assert [s[0] for s in result["steps"]] == [
        "generate data", "dbt seed", "dbt run", "dbt test", "dbt docs generate"]
    counts = result["tests"]["counts"]
    assert counts.get("pass", 0) == 48 and not counts.get("fail") and not counts.get("error")


def test_failing_dbt_test_fails_the_flow_without_retrying(monkeypatch):
    """A data-quality failure must surface as a failed run, and must not be retried."""
    calls = []

    def boom(cmd):
        calls.append(cmd)
        if cmd[:2] == ["dbt", "test"]:
            raise recon_flow.DbtStepFailed("1 test failed")
        return "ok"

    monkeypatch.setattr(recon_flow, "_run", boom)
    with pytest.raises(recon_flow.DbtStepFailed):
        recon_flow.recon_pipeline(target="dev", generate=False, docs=False)
    assert sum(1 for c in calls if c[:2] == ["dbt", "test"]) == 1   # exactly one attempt


def test_transient_failure_is_retried(monkeypatch):
    attempts = {"n": 0}

    def flaky(cmd):
        if cmd[:2] == ["dbt", "seed"]:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise recon_flow.DbtStepFailed("temporary lock")
        return "ok"

    monkeypatch.setattr(recon_flow, "_run", flaky)
    monkeypatch.setattr(recon_flow, "_summarize", lambda: {"counts": {}, "elapsed": 0})
    recon_flow.recon_pipeline(target="dev", generate=False, docs=False)
    assert attempts["n"] == 2


def test_portability_lint_passes():
    r = subprocess.run([sys.executable, "scripts/portability_check.py"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
