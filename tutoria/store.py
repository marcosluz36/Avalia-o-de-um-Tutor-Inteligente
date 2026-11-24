"""Chroma persistente com publicação de gerações via manifesto atômico.

Chroma e JSON não compartilham transações. Só gerações publicadas são consultadas;
uma falha durante a inserção mantém a geração anterior utilizável.
"""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import math

from .types import Chunk, Hit, TutorError
from .util import atomic_json, data_lock, digest, read_json


class VectorStore:
    def __init__(self, root: Path, embedding_profile: dict):
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.root = root
        self.dimension = embedding_profile["dimension"]
        with data_lock(root):
            self.client = chromadb.PersistentClient(path=str(root / "chroma"), settings=ChromaSettings(anonymized_telemetry=False))
            self.collection = self.client.get_or_create_collection(
                name="circuitos_logicos", embedding_function=None,
                configuration={"hnsw": {"space": "cosine"}},
                metadata={"embedding_profile_hash": digest(embedding_profile), "metric": "cosine_distance"},
            )
            if (self.collection.metadata or {}).get("embedding_profile_hash") != digest(embedding_profile):
                raise TutorError("A coleção usa outro contrato de embeddings. Escolha outra pasta de dados e reindexe.")

    def manifest(self) -> dict:
        value = read_json(self.root / "manifest.json", {"schema": 1, "documents": {}})
        if value.get("schema") != 1 or not isinstance(value.get("documents"), dict):
            raise TutorError("Manifesto de indexação inválido. Restaure a base ou use outra pasta.")
        return value

    def documents(self) -> list[dict]:
        with data_lock(self.root):
            return list(self.manifest()["documents"].values())

    def intact(self, record: dict) -> bool:
        ids = self.collection.get(where={"generation": record["generation"]}, include=[])["ids"]
        return len(ids) == record["chunk_count"]

    def replace_document(self, doc_id: str, signature: str, chunks: list[Chunk],
                         vectors: list[list[float]], warnings: list[str]) -> dict:
        """O chamador mantém data_lock durante checagem, preparação e commit."""
        if not chunks or len(chunks) != len(vectors):
            raise TutorError("Quantidade de chunks e vetores inconsistente; nada foi publicado.")
        for vector in vectors:
            if len(vector) != self.dimension or not all(math.isfinite(v) for v in vector):
                raise TutorError("Vetor inválido; nada foi publicado.")
            if not math.isclose(sum(v * v for v in vector), 1.0, abs_tol=0.005):
                raise TutorError("O vetor não está normalizado conforme o contrato da base.")
        manifest = deepcopy(self.manifest())
        generation = uuid4().hex
        record = {
            "document_id": doc_id, "signature": signature, "generation": generation,
            "filename": chunks[0].metadata["filename"], "material_title": chunks[0].metadata["material_title"],
            "chunk_count": len(chunks), "warnings": warnings,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            for start in range(0, len(chunks), 128):
                batch = chunks[start:start + 128]
                self.collection.upsert(
                    ids=[generation + ":" + c.id for c in batch],
                    documents=[c.text for c in batch], embeddings=vectors[start:start + 128],
                    metadatas=[{
                        "generation": generation, "document_id": doc_id, "chunk_id": c.id,
                        "contextualized_text": c.contextualized_text,
                        "source_metadata": json.dumps(c.metadata, ensure_ascii=False),
                    } for c in batch],
                )
            if not self.intact(record):
                raise ValueError("Incomplete generation")
            manifest["documents"][doc_id] = record
            atomic_json(self.root / "manifest.json", manifest)
        except Exception:
            # Não publica conjunto parcial; a geração anterior continua selecionada.
            # Não removemos uma geração se o estado de commit for incerto.
            raise TutorError("Falha ao publicar o índice. A versão anterior permanece selecionada se o commit não ocorreu. Tente a indexação novamente.") from None
        # Limpeza posterior ao commit: uma falha aqui não invalida o novo índice.
        try:
            self.collection.delete(where={"$and": [{"document_id": doc_id}, {"generation": {"$ne": generation}}]})
        except Exception:
            record["cleanup_warning"] = "Há vetores antigos não publicados; eles não entram nas consultas."
        return record

    @staticmethod
    def decode(chunk_id: str, text: str, metadata: dict) -> Chunk:
        return Chunk(metadata["chunk_id"], text, metadata["contextualized_text"], json.loads(metadata["source_metadata"]))

    def search(self, vector: list[float], k: int) -> list[Hit]:
        with data_lock(self.root):
            docs = list(self.manifest()["documents"].values())
            if not docs:
                return []
            result = self.collection.query(
                query_embeddings=[vector], n_results=min(k, sum(d["chunk_count"] for d in docs)),
                where={"generation": {"$in": [d["generation"] for d in docs]}},
                include=["documents", "metadatas", "distances"],
            )
            return [Hit(self.decode(cid, text, meta), i + 1, float(distance))
                    for i, (cid, text, meta, distance) in enumerate(zip(
                        result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True))]

    def get_chunk(self, chunk_id: str) -> Chunk:
        with data_lock(self.root):
            generations = [d["generation"] for d in self.manifest()["documents"].values()]
            if generations:
                result = self.collection.get(
                    where={"$and": [{"chunk_id": chunk_id}, {"generation": {"$in": generations}}]},
                    include=["documents", "metadatas"], limit=1,
                )
                if result["ids"]:
                    return self.decode(result["ids"][0], result["documents"][0], result["metadatas"][0])
        raise TutorError("Chunk não encontrado na base ativa. Respostas antigas mantêm uma cópia dos trechos em seu histórico/exportação.")

    def remove(self, doc_id: str) -> None:
        with data_lock(self.root):
            manifest = self.manifest()
            if doc_id not in manifest["documents"]:
                raise TutorError("Documento não encontrado. Use o ID completo mostrado em list.")
            del manifest["documents"][doc_id]
            atomic_json(self.root / "manifest.json", manifest)
            # Originais, extrações e cache de chunks são preservados para reindexar.
            self.collection.delete(where={"document_id": doc_id})
