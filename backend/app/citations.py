"""Build trusted source metadata from retrieved chunks after the model selects supporting IDs."""

from app.errors import ProviderError
from app.schemas import SearchHit, Source


def build_citations(hits: list[SearchHit], source_ids: list[int]) -> list[Source]:
    """Validate model-selected IDs and generate numbered citations solely from database results."""
    by_id = {hit.chunk_id: hit for hit in hits}
    unique_ids = list(dict.fromkeys(source_ids))
    if any(chunk_id not in by_id for chunk_id in unique_ids):
        raise ProviderError("The model referenced an unknown source. Please retry the question.")
    sources = []
    for number, chunk_id in enumerate(unique_ids, 1):
        hit = by_id[chunk_id]
        sources.append(
            Source(
                **hit.model_dump(exclude={"text"}),
                citation=number,
                excerpt=hit.text,
            )
        )
    return sources
