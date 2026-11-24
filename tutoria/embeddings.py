"""Embeddings E5 em CPU; revisão e contrato persistidos por base."""

from pathlib import Path
import re

from .config import EMBED_MODEL, Settings
from .types import TutorError
from .util import atomic_json, data_lock, package_version, read_json


class E5Embedder:
    model_id = EMBED_MODEL
    dimension = 384
    max_tokens = 512
    passage_prefix = "passage: "
    query_prefix = "query: "

    def __init__(self, settings: Settings):
        from huggingface_hub import hf_hub_download
        from sentence_transformers import SentenceTransformer

        self.batch_size = settings.embedding_batch_size
        profile_path = settings.data_dir / "embedding_profile.json"
        versions = {p: package_version(p) for p in ("sentence-transformers", "transformers", "torch")}
        with data_lock(settings.data_dir):
            saved = read_json(profile_path)
            requested = settings.embedding_revision
            if saved:
                revision = saved["revision"]
                if requested != "main" and requested != revision:
                    raise TutorError("A revisão de embeddings difere da base. Use outra TUTORIA_DATA_DIR.")
            else:
                try:
                    cached_config = hf_hub_download(self.model_id, "config.json", revision=requested)
                    revision = Path(cached_config).parent.name
                    if not re.fullmatch(r"[0-9a-f]{40}", revision):
                        raise ValueError("Unresolved revision")
                except Exception:
                    raise TutorError("Não foi possível baixar o modelo de embeddings. Confira a rede e o cache do Hugging Face.") from None
            self.profile = {
                "schema": 1, "model": self.model_id, "revision": revision,
                "dimension": self.dimension, "max_tokens": self.max_tokens,
                "normalize": True, "pooling": "mean", "device": "cpu",
                "passage_prefix": self.passage_prefix, "query_prefix": self.query_prefix,
                "versions": versions,
            }
            if saved and saved != self.profile:
                raise TutorError("O contrato de embeddings mudou (modelo/configuração/bibliotecas). Restaure as versões anteriores ou use outra TUTORIA_DATA_DIR e reindexe.")
            try:
                self.model = SentenceTransformer(self.model_id, revision=revision, device="cpu", trust_remote_code=False)
                self.model.max_seq_length = self.max_tokens
                self.tokenizer = self.model.tokenizer
                if self.model.get_sentence_embedding_dimension() != self.dimension:
                    raise ValueError("Unexpected dimension")
            except Exception:
                raise TutorError("Falha ao carregar embeddings em CPU. Confira instalação, rede, cache e memória disponível.") from None
            if not saved:
                atomic_json(profile_path, self.profile)

    def token_count(self, text: str, kind: str = "passage") -> int:
        prefix = self.passage_prefix if kind == "passage" else self.query_prefix
        return len(self.tokenizer.encode(prefix + text, add_special_tokens=True, truncation=False))

    def _encode(self, texts: list[str], kind: str) -> list[list[float]]:
        if any(self.token_count(t, kind) > self.max_tokens for t in texts):
            message = ("Um chunk excedeu 512 tokens, incluindo títulos e prefixo. Reduza TUTORIA_CHUNK_TOKENS e reindexe. Nenhum texto será truncado silenciosamente."
                       if kind == "passage" else "A pergunta excede o limite do modelo de busca. Divida-a em perguntas menores.")
            raise TutorError(message)
        prefix = self.passage_prefix if kind == "passage" else self.query_prefix
        try:
            return self.model.encode(
                [prefix + t for t in texts], batch_size=self.batch_size,
                normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
            ).tolist()
        except Exception:
            raise TutorError("Falha na geração de embeddings. Reduza TUTORIA_EMBED_BATCH_SIZE se faltar memória.") from None

    def passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts, "passage")

    def query(self, text: str) -> list[float]:
        return self._encode([text], "query")[0]
