"""Contratos compartilhados. Sem dependências de infraestrutura."""

from dataclasses import asdict, dataclass, field
from typing import Any


class TutorError(Exception):
    """Erro com mensagem segura para exibição; nunca contém credenciais."""


@dataclass
class Chunk:
    id: str
    text: str
    contextualized_text: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Hit:
    chunk: Chunk
    rank: int
    distance: float
    eligible: bool = True

    @property
    def similarity(self) -> float:
        return 1.0 - self.distance


@dataclass(frozen=True)
class QuerySettings:
    model: str = "openai/gpt-4o-mini"
    temperature: float = 0.2
    k: int = 4
    max_tokens: int = 300
    min_similarity: float = 0.75

    def validate(self) -> None:
        if not self.model.strip() or "/" not in self.model or any(c.isspace() for c in self.model):
            raise TutorError("Informe o identificador completo do modelo, por exemplo openai/gpt-4o-mini.")
        if not 0 <= self.temperature <= 2:
            raise TutorError("A temperatura deve estar entre 0 e 2.")
        if not 1 <= self.k <= 20:
            raise TutorError("k deve estar entre 1 e 20.")
        if not 32 <= self.max_tokens <= 16384:
            raise TutorError("O teto de saída deve estar entre 32 e 16384 tokens.")
        if not -1 <= self.min_similarity <= 1:
            raise TutorError("A similaridade mínima deve estar entre -1 e 1.")


@dataclass(frozen=True)
class ModelCaps:
    id: str
    context_length: int
    max_completion_tokens: int | None
    parameters: tuple[str, ...]


@dataclass
class ContextPlan:
    messages: list[dict[str, str]]
    sent: dict[str, Hit]
    estimated_input: int
    input_budget: int
    output_tokens: int
    history_turns_sent: int
    notices: list[str] = field(default_factory=list)
