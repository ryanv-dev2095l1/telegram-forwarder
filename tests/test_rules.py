import pytest
from telegram_forwarder.rules import ForwardRule, evaluate_rules


def test_single_keyword_match():
    rule = ForwardRule(
        name="alerts",
        include_regex=[r"(?i)\b(cve-\d{4}-\d+|critical vuln)"],
        exclude_regex=[],
        channels=[100123],
        target_chats=[200456],
        webhook_urls=[],
    )

    matched = evaluate_rules([rule], "New release fixes CVE-2024-1234 in core", 100123)
    assert len(matched) == 1
    assert matched[0].name == "alerts"


def test_channel_id_mismatch():
    rule = ForwardRule(
        name="alerts",
        include_regex=[r"critical"],
        exclude_regex=[],
        channels=[100123],
        target_chats=[],
        webhook_urls=[],
    )

    # Right text, wrong channel
    assert evaluate_rules([rule], "this is critical", 999999) == []


def test_wildcard_channel_list():
    rule = ForwardRule(
        name="catchall",
        include_regex=[r"deploy"],
        exclude_regex=[],
        channels=[],  # Empty list acts as wildcard across all configured streams
        target_chats=[],
        webhook_urls=["http://localhost:8080/hook"],
    )

    assert len(evaluate_rules([rule], "start deploy step 1", 5555)) == 1
    assert len(evaluate_rules([rule], "start deploy step 1", 7777)) == 1


def test_exclude_regex_overrides_include():
    rule = ForwardRule(
        name="crypto",
        include_regex=[r"(?i)bitcoin|eth"],
        exclude_regex=[r"(?i)sponsored|giveaway|airdrop"],
        channels=[100],
        target_chats=[],
        webhook_urls=[],
    )

    assert evaluate_rules([rule], "Bitcoin hits 90k today!", 100) == [rule]
    assert evaluate_rules([rule], "Bitcoin giveaway! Click here", 100) == []


def test_multiline_matching():
    rule = ForwardRule(
        name="stacktrace",
        include_regex=[r"Traceback \(most recent call last\):[\s\S]+ZeroDivisionError"],
        exclude_regex=[],
        channels=[100],
        target_chats=[],
        webhook_urls=[],
    )

    text = """Traceback (most recent call last):
  File "run.py", line 4, in <module>
    1 / 0
ZeroDivisionError: division by zero"""

    assert len(evaluate_rules([rule], text, 100)) == 1
