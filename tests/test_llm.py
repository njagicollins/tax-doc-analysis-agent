import os
from types import SimpleNamespace

import pytest
from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel

from taxagent.agent.llm import LLM, LLMError, llm_from_env
from taxagent.agent.pii import PiiLeakError

ROSTER = {"E007": "Patrick Sanchez"}
MODELS = {"small": "tiny-model", "large": "big-model"}


class Answer(BaseModel):
    text: str


class FakeClient:
    """Stands in for OpenAI: records every request, returns a canned answer."""

    def __init__(self, answer):
        self.requests = []
        self.responses = self  # so code can call client.responses.parse(...)
        self.answer = answer

    def parse(self, **request):
        self.requests.append(request)
        return SimpleNamespace(output_parsed=self.answer)


def test_returns_the_parsed_answer():
    llm = LLM(FakeClient(Answer(text="hi")), MODELS, ROSTER)

    assert llm.parse("small", "be brief", "say hi", Answer) == Answer(text="hi")


@pytest.mark.parametrize(
    ("role", "model"), [("small", "tiny-model"), ("large", "big-model")]
)
def test_role_picks_the_model_from_config(role, model):
    client = FakeClient(Answer(text="ok"))

    LLM(client, MODELS, ROSTER).parse(role, "x", "y", Answer)

    assert client.requests[0]["model"] == model


def test_personal_data_never_leaves():
    client = FakeClient(Answer(text="ok"))
    llm = LLM(client, MODELS, ROSTER)

    with pytest.raises(PiiLeakError):
        llm.parse("small", "x", "Why was Patrick Sanchez paid more?", Answer)
    assert client.requests == []  # blocked before any request was made


def test_empty_output_fails_loudly():
    llm = LLM(FakeClient(None), MODELS, ROSTER)

    with pytest.raises(LLMError, match="big-model"):
        llm.parse("large", "x", "y", Answer)


def test_openai_provider_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("MODEL_SMALL", "tiny-model")
    monkeypatch.setenv("MODEL_LARGE", "big-model")

    llm = llm_from_env(ROSTER)

    assert isinstance(llm.client, OpenAI)
    assert llm.models == MODELS


def test_azure_is_a_config_change(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    monkeypatch.setenv("MODEL_SMALL", "tiny-deployment")
    monkeypatch.setenv("MODEL_LARGE", "big-deployment")

    assert isinstance(llm_from_env(ROSTER).client, AzureOpenAI)


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mystery")

    with pytest.raises(ValueError, match="mystery"):
        llm_from_env(ROSTER)


def openai_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("MODEL_SMALL", "tiny-model")
    monkeypatch.setenv("MODEL_LARGE", "big-model")


def test_tracing_is_off_unless_switched_on(monkeypatch):
    openai_env(monkeypatch)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)

    llm = llm_from_env(ROSTER)

    assert not hasattr(llm.client.responses.parse, "__wrapped__")  # not traced


def test_switching_tracing_on_traces_every_llm_call(monkeypatch):
    openai_env(monkeypatch)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    llm = llm_from_env(ROSTER)

    assert hasattr(llm.client.responses.parse, "__wrapped__")  # wrapped by LangSmith


def test_the_tests_themselves_never_trace():
    assert os.environ["LANGSMITH_TRACING"] == "false"  # set in conftest.py
