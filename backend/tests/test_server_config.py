"""
Tests for server/config.py — validates all constants are defined and have the expected values.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.config import (
    RABBITMQ_HOST,
    RUN_EXCHANGE, SUBMIT_EXCHANGE,
    RUN_ROUTING_KEY, SUBMIT_ROUTING_KEY,
    RUN_QUEUE, SUBMIT_QUEUE,
)


def test_rabbitmq_host_is_string():
    assert isinstance(RABBITMQ_HOST, str)
    assert RABBITMQ_HOST == 'localhost'


def test_exchange_names_are_distinct():
    assert RUN_EXCHANGE != SUBMIT_EXCHANGE


def test_routing_keys_are_distinct():
    assert RUN_ROUTING_KEY != SUBMIT_ROUTING_KEY


def test_queue_names_are_distinct():
    assert RUN_QUEUE != SUBMIT_QUEUE


def test_all_constants_are_non_empty_strings():
    constants = [
        RABBITMQ_HOST, RUN_EXCHANGE, SUBMIT_EXCHANGE,
        RUN_ROUTING_KEY, SUBMIT_ROUTING_KEY, RUN_QUEUE, SUBMIT_QUEUE,
    ]
    for c in constants:
        assert isinstance(c, str) and c, f"Expected non-empty string, got: {c!r}"
