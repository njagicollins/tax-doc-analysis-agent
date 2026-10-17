"""The one doorway to the LLM.

Every call goes through LLM.parse(), so every call is PII-checked, routed to the
right model by config, and returns validated structured output (never free text
that we would have to guess how to read).
"""

import os
from typing import Any, TypeVar

from langsmith.wrappers import wrap_openai
from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel

from taxagent.agent.pii import assert_no_pii

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """The model did not return usable output."""


class LLM:
    def __init__(self, client: Any, models: dict[str, str], roster: dict[str, str]):
        self.client = client  # OpenAI or AzureOpenAI; tests pass a fake
        self.models = models  # role -> model name, e.g. {"small": "gpt-4o-mini"}
        self.roster = roster  # employee ID -> name, for the PII guard

    def parse(self, role: str, instructions: str, prompt: str, schema: type[T]) -> T:
        # The guard sits in the doorway, so no caller can forget it
        assert_no_pii(instructions + "\n" + prompt, self.roster)

        response = self.client.responses.parse(
            model=self.models[role],
            instructions=instructions,
            input=prompt,
            text_format=schema,
            temperature=0,  # less randomness; still not fully deterministic
        )
        if response.output_parsed is None:
            raise LLMError(f"{self.models[role]} returned no {schema.__name__}")
        return response.output_parsed


def tracing_on() -> bool:
    """LangSmith tracing is off unless .env switches it on: traces leave this machine."""
    return os.environ.get("LANGSMITH_TRACING", "").lower() == "true"


def llm_from_env(roster: dict[str, str]) -> LLM:
    """Pick the provider from config: moving to Azure is a .env change, not a rewrite."""
    provider = os.environ.get("LLM_PROVIDER", "openai")
    if provider == "openai":
        client = OpenAI()  # reads OPENAI_API_KEY
    elif provider == "azure":
        client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER {provider!r}: use 'openai' or 'azure'")
    if tracing_on():
        client = wrap_openai(client)  # each LLM call also shows up in LangSmith

    # On Azure these are deployment names; on OpenAI, model names
    models = {"small": os.environ["MODEL_SMALL"], "large": os.environ["MODEL_LARGE"]}
    return LLM(client, models, roster)
