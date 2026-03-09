"""
Tests for server/models.py — Pydantic model validation.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from pydantic import ValidationError
from server.models import SubmitRequest, RunRequest


# ---------------------------------------------------------------------------
# SubmitRequest
# ---------------------------------------------------------------------------

SUBMIT_DEFAULTS = dict(
    problem_id=1,
    language="cpp",
    src_code='#include<stdio.h>\nint main(){}',
)


def test_submit_request_valid():
    req = SubmitRequest(**SUBMIT_DEFAULTS)
    assert req.language == "cpp"
    assert req.problem_id == 1


def test_submit_request_missing_required_field():
    data = {k: v for k, v in SUBMIT_DEFAULTS.items() if k != "problem_id"}
    with pytest.raises(ValidationError):
        SubmitRequest(**data)


def test_submit_request_wrong_type_for_problem_id():
    with pytest.raises(ValidationError):
        SubmitRequest(**{**SUBMIT_DEFAULTS, "problem_id": "two"})


def test_submit_request_dict_round_trip():
    req = SubmitRequest(**SUBMIT_DEFAULTS)
    d = req.model_dump()
    assert d["language"] == "cpp"
    assert d["problem_id"] == 1


# ---------------------------------------------------------------------------
# RunRequest
# ---------------------------------------------------------------------------

RUN_DEFAULTS = dict(
    language="py",
    time_limit=5,
    memory_limit=128,
    src_code="print(42)",
    callback_url="http://localhost:8080/callback",
)


def test_run_request_valid():
    req = RunRequest(**RUN_DEFAULTS)
    assert req.language == "py"
    assert req.std_in == " "  # default


def test_run_request_custom_stdin():
    req = RunRequest(**{**RUN_DEFAULTS, "std_in": "hello"})
    assert req.std_in == "hello"


def test_run_request_missing_callback_url_is_allowed():
    data = {k: v for k, v in RUN_DEFAULTS.items() if k != "callback_url"}
    req = RunRequest(**data)
    assert req.callback_url is None

def test_run_request_dict_round_trip():
    req = RunRequest(**RUN_DEFAULTS)
    d = req.model_dump()
    assert d["callback_url"] == RUN_DEFAULTS["callback_url"]
    assert d["language"] == "py"
