"""Complete the query pipeline by combining retrieval, generation, and verified citations."""

from app.citations import build_citations
from app.llm import LanguageModel
from app.prompts import NOT_FOUND, build_prompt
from app.retrieval import RetrievalService
from app.schemas import ChatResponse


class ChatService:
    """Compose retrieval and generation services without hiding their intermediate steps."""

    def __init__(self, retrieval: RetrievalService, model: LanguageModel):
        """Accept explicit dependencies so chat tests can avoid paid network calls."""
        self.retrieval, self.model = retrieval, model

    def query(self, question: str, document_ids: list[int] | None, top_k: int) -> ChatResponse:
        """Retrieve, generate, validate source IDs, then append application-made citations."""
        hits = self.retrieval.search(question, document_ids, top_k)
        if not hits:
            return ChatResponse(answer=NOT_FOUND, sources=[])
        result = self.model.answer(build_prompt(question, hits))
        if not result.source_ids or not result.answer.strip():
            return ChatResponse(answer=NOT_FOUND, sources=[])
        sources = build_citations(hits, result.source_ids)
        labels = " ".join(f"[{source.citation}]" for source in sources)
        return ChatResponse(answer=f"{result.answer.strip()} {labels}", sources=sources)
