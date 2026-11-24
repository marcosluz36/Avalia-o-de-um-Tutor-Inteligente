from dataclasses import dataclass
from pathlib import Path
import os

from .types import TutorError

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".md"}
EMBED_MODEL = "intfloat/multilingual-e5-small"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    chunk_tokens: int = 480
    ocr: bool = False
    formulas: bool = False
    embedding_revision: str = "main"
    embedding_batch_size: int = 16

    @classmethod
    def from_env(cls) -> "Settings":
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
        try:
            settings = cls(
                data_dir=Path(os.getenv("TUTORIA_DATA_DIR", str(ROOT / "data"))).expanduser().resolve(),
                chunk_tokens=int(os.getenv("TUTORIA_CHUNK_TOKENS", "480")),
                ocr=os.getenv("TUTORIA_OCR", "false").lower() in {"1", "true", "yes"},
                formulas=os.getenv("TUTORIA_FORMULAS", "false").lower() in {"1", "true", "yes"},
                embedding_revision=os.getenv("TUTORIA_EMBED_REVISION", "main"),
                embedding_batch_size=int(os.getenv("TUTORIA_EMBED_BATCH_SIZE", "16")),
            )
        except ValueError:
            raise TutorError("Confira os valores numéricos do arquivo .env.") from None
        if not 64 <= settings.chunk_tokens <= 480:
            raise TutorError("TUTORIA_CHUNK_TOKENS deve estar entre 64 e 480.")
        if not 1 <= settings.embedding_batch_size <= 128:
            raise TutorError("TUTORIA_EMBED_BATCH_SIZE deve estar entre 1 e 128.")
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        return settings
