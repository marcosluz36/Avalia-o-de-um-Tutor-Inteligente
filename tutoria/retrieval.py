"""Busca vetorial explícita; k pertence à recuperação, não à amostragem."""

import math
import re

from .types import TutorError

FOLLOW_UP = re.compile(
    r"^(?:não entendi|nao entendi|não sei|nao sei|continue|continua|explique melhor|"
    r"mais (?:uma )?pista|outra pista|dê (?:mais )?uma pista|de uma pista|"
    r"mostre (?:a )?solução|mostre (?:a )?solucao|resolva (?:tudo|completo)|"
    r"solução (?:completa|detalhada)|solucao (?:completa|detalhada)|"
    r"por qu[eê]|e (?:se|isso|nesse|neste)|como assim|sim\b|não\b|nao\b|"
    r"(?:acho|penso) que|(?:a resposta|o resultado) é|[01](?:\b|\s))", re.I,
)


def search_query(question: str, history: list[dict], embedder) -> str:
    """Continuações curtas recuperam o enunciado anterior sem uma segunda LLM."""
    if embedder.token_count(question, "query") > embedder.max_tokens:
        raise TutorError("A pergunta é longa demais para a busca. Divida o enunciado em partes menores.")
    if len(question.split()) <= 35 and FOLLOW_UP.search(question.strip()):
        previous = next((h["question"] for h in reversed(history)
                         if not FOLLOW_UP.search(h["question"].strip())), None)
        if previous:
            combined = f"Assunto/enunciado anterior: {previous}\nPergunta atual: {question}"
            # Reduz apenas o texto auxiliar antigo, nunca a pergunta atual.
            while previous and embedder.token_count(combined, "query") > embedder.max_tokens:
                previous = previous[:len(previous) * 3 // 4]
                combined = f"Assunto/enunciado anterior: {previous}\nPergunta atual: {question}"
            if previous:
                return combined
    return question


def retrieve(question: str, history: list[dict], embedder, store, k: int,
             min_similarity: float) -> tuple[str, list]:
    query = search_query(question, history, embedder)
    hits = store.search(embedder.query(query), k)
    for hit in hits:
        if not math.isfinite(hit.distance):
            raise TutorError("A base retornou uma distância inválida. Verifique/reindexe os vetores.")
        hit.eligible = hit.similarity >= min_similarity
    return query, hits
