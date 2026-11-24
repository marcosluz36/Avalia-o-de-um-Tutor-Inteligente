"""HybridChunker estrutural + refinamento por tokens; não é busca híbrida."""

from .types import Chunk, TutorError
from .util import digest


def provenance(items, format_name: str, pdf_labels: dict, printed_map: dict) -> dict:
    locations, pages = [], set()
    for item in items:
        for prov in getattr(item, "prov", []):
            page = getattr(prov, "page_no", None)
            if isinstance(page, int) and page > 0:
                pages.add(page)
            bbox = getattr(prov, "bbox", None)
            locations.append({
                "item_ref": getattr(item, "self_ref", None), "page_no": page,
                "bbox": bbox.model_dump(mode="json") if bbox is not None else None,
                "charspan": list(prov.charspan) if getattr(prov, "charspan", None) is not None else None,
            })
    numbers = sorted(pages)
    return {
        "pdf_pages": numbers if format_name == "pdf" else [],
        "slides": numbers if format_name == "pptx" else [],
        "docling_pages": numbers,
        "pdf_page_labels": [{"pdf_page": n, "label": pdf_labels[str(n)]} for n in numbers if str(n) in pdf_labels] if format_name == "pdf" else [],
        "printed_pages": [{"pdf_page": n, "printed_page": printed_map[str(n)]} for n in numbers if str(n) in printed_map] if format_name == "pdf" else [],
        "printed_page_origin": "user_mapping" if printed_map and format_name == "pdf" else None,
        "provenance": locations,
    }


def make_chunks(extraction, embedder, doc_id: str, signature: str, filename: str,
                max_tokens: int, title: str | None = None, printed_map: dict | None = None) -> list[Chunk]:
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

    tokenizer = HuggingFaceTokenizer(tokenizer=embedder.tokenizer, max_tokens=max_tokens)
    chunker = HybridChunker(tokenizer=tokenizer, merge_peers=True)
    result = []
    for index, part in enumerate(chunker.chunk(dl_doc=extraction.document)):
        if not part.text.strip():
            continue
        enriched = chunker.contextualize(chunk=part)
        token_count = embedder.token_count(enriched)
        if token_count > embedder.max_tokens:
            raise TutorError("O HybridChunker produziu um trecho maior que o limite do embedding. Reduza TUTORIA_CHUNK_TOKENS; a indexação foi interrompida para evitar truncamento.")
        base = extraction.metadata
        headings = list(getattr(part.meta, "headings", None) or [])
        metadata = {
            "document_id": doc_id, "filename": filename,
            "material_title": title or base["material_title"],
            "title_origin": "user" if title else base["title_origin"],
            "headings": headings, "section": " > ".join(headings) or None,
            "format": base["format"], "ordinal": index,
            "embedding_tokens": token_count,
            "source_path": base["source_path"],
            "extracted_markdown_path": base["extracted_markdown_path"],
            "docling_json_path": base["docling_json_path"],
            "index_signature": signature,
            "extraction_warnings": list(extraction.warnings),
            **provenance(part.meta.doc_items, base["format"], base["pdf_page_labels"], printed_map or {}),
        }
        chunk_id = digest({"document": doc_id, "signature": signature, "ordinal": index, "text": part.text, "context": enriched})
        result.append(Chunk(chunk_id, part.text, enriched, metadata))
    if not result:
        raise TutorError("Nenhum chunk textual foi produzido. Confira o texto extraído e a configuração de OCR.")
    return result
