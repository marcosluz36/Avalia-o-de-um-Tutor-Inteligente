"""Orquestra extração, chunking, embeddings e publicação; nenhuma LLM é usada."""

from pathlib import Path

from .chunking import make_chunks
from .config import SUPPORTED_EXTENSIONS
from .extraction import extract, extraction_profile
from .types import Chunk, TutorError
from .util import atomic_json, data_lock, digest, read_json, safe_name


def index_document(content: bytes, filename: str, settings, embedder, store,
                   force: bool = False, title: str | None = None, printed_map: dict | None = None,
                   progress=lambda message: None) -> dict:
    filename = safe_name(filename)
    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise TutorError("Formato não implementado. Use PDF, DOCX, PPTX ou Markdown (.md).")
    if not content or len(content) > 100 * 1024 * 1024:
        raise TutorError("Envie um arquivo não vazio de até 100 MB. Divida materiais maiores.")
    printed_map = {str(k): str(v) for k, v in (printed_map or {}).items()}
    if any(not k.isdigit() or int(k) < 1 or not v.strip() for k, v in printed_map.items()):
        raise TutorError("O mapa de páginas deve associar páginas PDF positivas a números/rótulos impressos não vazios.")
    if printed_map and Path(filename).suffix.lower() != ".pdf":
        raise TutorError("O mapeamento de páginas impressas é implementado apenas para PDF.")
    doc_id = digest(content)
    signature = digest({
        "schema": 1, "embedding": embedder.profile, "extraction": extraction_profile(settings),
        "chunking": {"type": "docling.HybridChunker", "tokens": settings.chunk_tokens, "merge_peers": True},
        "format": Path(filename).suffix.lower(), "title": title or None, "printed_map": printed_map,
    })
    with data_lock(settings.data_dir):
        existing = store.manifest()["documents"].get(doc_id)
        if existing and existing["signature"] == signature and not force and store.intact(existing):
            return {**existing, "status": "already_indexed"}
        source = settings.data_dir / "originals" / doc_id / filename
        source.parent.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            source.write_bytes(content)
        elif digest(source.read_bytes()) != doc_id:
            raise TutorError("A cópia local do original foi alterada. Restaure-a antes de reindexar.")
        progress("Extraindo e estruturando o material com Docling…")
        extracted = extract(source, doc_id, settings, force)
        count = extracted.metadata.get("pdf_page_count")
        if printed_map and (count is None or any(int(k) > count for k in printed_map)):
            raise TutorError("O mapa de páginas contém uma página inexistente ou o PDF não pôde ser contado.")
        cache = settings.data_dir / "chunks" / doc_id / (signature + ".json")
        cached = read_json(cache) if not force else None
        if cached:
            chunks = [Chunk(**c) for c in cached]
        else:
            progress("Criando chunks com o tokenizer dos embeddings…")
            chunks = make_chunks(extracted, embedder, doc_id, signature, filename, settings.chunk_tokens, title, printed_map)
            atomic_json(cache, [c.to_dict() for c in chunks])
        texts = [c.contextualized_text for c in chunks]
        vector_key = digest({"profile": embedder.profile, "texts": texts})
        vector_cache = settings.data_dir / "embeddings" / doc_id / (vector_key + ".json")
        vectors = read_json(vector_cache) if not force else None
        if vectors is None:
            progress(f"Gerando embeddings de {len(chunks)} chunks em CPU…")
            vectors = embedder.passages(texts)
            atomic_json(vector_cache, vectors)
        else:
            progress("Reaproveitando embeddings com texto e contrato idênticos…")
        progress("Publicando o índice persistente…")
        record = store.replace_document(doc_id, signature, chunks, vectors, extracted.warnings)
        return {**record, "status": "indexed"}
