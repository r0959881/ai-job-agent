"""Two Groq keys: the second takes over when the first reaches its limit."""
import httpx
import pytest
from groq import APIConnectionError, RateLimitError

import tailor


def rate_limited(wait="9m33.696s"):
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
    return RateLimitError(f"Rate limit reached on tokens per day (TPD). Please try again in {wait}.",
                          response=response, body=None)


class FakeGroq:
    """Stands in for groq.Groq: each key answers or raises what the test set for it."""

    behaviour = {}
    calls = []

    def __init__(self, api_key):
        self.key = api_key
        completions = type("Completions", (), {"create": lambda _self, **kwargs: self.answer(kwargs)})()
        self.chat = type("Chat", (), {"completions": completions})()

    def answer(self, kwargs):
        FakeGroq.calls.append(self.key)
        outcome = FakeGroq.behaviour.get(self.key, "ok")
        if isinstance(outcome, Exception):
            raise outcome
        return f"answer from {self.key}"


@pytest.fixture(autouse=True)
def fake_groq(monkeypatch):
    FakeGroq.behaviour, FakeGroq.calls = {}, []
    monkeypatch.setattr(tailor, "Groq", FakeGroq)
    monkeypatch.setattr(tailor, "_spent_until", {})
    monkeypatch.setenv("GROQ_API_KEY", "gsk_first")
    monkeypatch.setenv("GROQ_API_KEY_2", "gsk_second")


def ask():
    return tailor.get_client().chat.completions.create(model="m", messages=[])


def test_the_second_key_answers_when_the_first_reaches_its_limit():
    assert ask() == "answer from gsk_first"

    FakeGroq.behaviour["gsk_first"] = rate_limited()
    assert ask() == "answer from gsk_second"  # the same request, answered by the backup key
    FakeGroq.calls.clear()
    assert ask() == "answer from gsk_second"
    assert FakeGroq.calls == ["gsk_second"]  # the spent key rests until Groq's reset time


def test_the_first_key_is_used_again_once_its_limit_resets(monkeypatch):
    FakeGroq.behaviour["gsk_first"] = rate_limited(wait="0.01s")
    assert ask() == "answer from gsk_second"
    FakeGroq.behaviour.clear()
    monkeypatch.setattr(tailor.time, "monotonic", lambda: 10**9)  # long after the reset
    assert ask() == "answer from gsk_first"


def test_when_both_keys_are_spent_the_limit_error_is_raised():
    FakeGroq.behaviour.update(gsk_first=rate_limited(), gsk_second=rate_limited())
    with pytest.raises(RateLimitError):
        ask()


def test_other_errors_do_not_switch_keys():
    request = httpx.Request("POST", "https://api.groq.com")
    FakeGroq.behaviour["gsk_first"] = APIConnectionError(request=request)
    with pytest.raises(APIConnectionError):
        ask()
    assert FakeGroq.calls == ["gsk_first"]


def test_one_key_is_enough_and_a_backup_alone_works(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY_2")
    assert tailor.groq_keys() == ["gsk_first"] and ask() == "answer from gsk_first"
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.setenv("GROQ_API_KEY_2", "gsk_second")
    assert tailor.check_groq_key() == "gsk_second"
    monkeypatch.delenv("GROQ_API_KEY_2")
    with pytest.raises(tailor.GroqConfigError, match="No Groq API key"):
        tailor.check_groq_key()
