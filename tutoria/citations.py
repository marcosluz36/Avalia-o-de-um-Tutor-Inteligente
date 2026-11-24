"""Valida o pertencimento das referências; não valida implicação semântica."""

from dataclasses import dataclass
import re


@dataclass
class CitationResult:
    answer: str
    cited: list[str]
    invalid: list[str]
    status: str
    warning: str | None = None


def validate_citations(answer: str, allowed: set[str]) -> CitationResult:
    observed = re.findall(r"\[([Cc]\d[^\]\n]*)\]", answer)
    invalid = sorted({label for label in observed if label not in allowed})
    cited = sorted(set(observed) & allowed, key=lambda label: int(label[1:]))
    if invalid:
        return CitationResult(
            "A resposta gerada continha referências que não pertencem ao contexto enviado e foi descartada. Reformule a pergunta ou tente outro modelo.",
            cited, invalid, "citation_error",
            "A validação rejeitou referências inválidas: " + ", ".join(f"[{c}]" for c in invalid),
        )
    unsupported = answer.strip().startswith("[SEM_SUPORTE]")
    if not cited and not unsupported:
        return CitationResult(
            "O modelo não forneceu referências para sustentar a resposta. A saída foi descartada; tente reformular a pergunta ou usar outro modelo.",
            [], [], "citation_error", "Saída sem citações e sem declaração explícita de contexto insuficiente.",
        )
    if unsupported:
        answer = answer.strip()[len("[SEM_SUPORTE]"):].lstrip()
    if not answer.strip():
        answer = "Os trechos disponíveis são insuficientes. Envie o enunciado completo ou um material sobre o assunto."
    return CitationResult(answer, cited, [], "insufficient_support" if unsupported else "answered")
