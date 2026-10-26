"""Direct OpenAI Responses API integration; this module has no knowledge of FAISS or SQL."""

import logging
from typing import Protocol

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import Settings
from app.errors import ProviderError
from app.prompts import INSTRUCTIONS

logger = logging.getLogger(__name__)


class ModelAnswer(BaseModel):
    """
    Require answer text and supporting passage IDs; citation coordinates are not model
    outputs.
    """

    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str
    source_ids: list[int]


class LanguageModel(Protocol):
    """Allow deterministic generation tests while production uses the actual OpenAI client."""

    def answer(self, prompt: str) -> ModelAnswer:
        """
        Accept serialized retrieved context and return answer text plus claimed
        supporting IDs.
        """
        ...


class OpenAILanguageModel:
    """Generate a structured grounded response with no built-in retrieval tools."""

    def __init__(self, settings: Settings):
        """Keep model configuration separate from prompt construction and citation rendering."""
        self.settings = settings

    def answer(self, prompt: str) -> ModelAnswer:
        """
        Call Responses with a strict JSON schema, rejecting refusals, truncation, and
        bad output.
        """
        if not self.settings.openai_api_key:
            raise ProviderError("Set OPENAI_API_KEY in .env and restart the backend.")
        try:
            with OpenAI(api_key=self.settings.openai_api_key, timeout=60, max_retries=1) as client:
                response = client.responses.create(
                    model=self.settings.llm_model,
                    instructions=INSTRUCTIONS,
                    input=prompt,
                    store=False,
                    max_output_tokens=2000,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "grounded_answer",
                            "strict": True,
                            "schema": ModelAnswer.model_json_schema(),
                        }
                    },
                )
            if response.status != "completed" or not response.output_text:
                raise ProviderError(
                    "The model did not complete an answer. Try a more specific question."
                )
            result = ModelAnswer.model_validate_json(response.output_text)
        except OpenAIError as exc:
            logger.warning("LLM request failed: %s", type(exc).__name__)
            raise ProviderError(
                "OpenAI could not generate an answer. Check your API key, quota, and LLM_MODEL."
            ) from exc
        except ValidationError as exc:
            raise ProviderError(
                "The model returned an invalid answer format. Please retry."
            ) from exc
        logger.info("LLM response generated")
        return result
