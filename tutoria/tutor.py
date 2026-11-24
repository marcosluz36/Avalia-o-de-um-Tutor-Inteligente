"""Orquestra uma consulta e retorna uma fotografia independente de configurações futuras."""

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from .citations import validate_citations
from .context import build_context
from .openrouter import OpenRouter
from .retrieval import retrieve
from .types import TutorError
from .util import digest


def new_turn(question: str, settings) -> dict:
    return {
        "id": uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(),
        "question": question, "answer": "", "status": "pending",
        "settings": asdict(settings), "sources": [], "reference_map": {},
        "notices": [], "trace": {"metric": "cosine_distance", "similarity_formula": "1 - distance"},
    }


class Tutor:
    def __init__(self, embedder, store, router_factory=OpenRouter):
        self.embedder, self.store, self.router_factory = embedder, store, router_factory

    def ask(self, question: str, history: list[dict], settings, api_key: str) -> dict:
        turn = new_turn(question.strip(), settings)
        try:
            settings.validate()
            if not question.strip():
                raise TutorError("Digite uma pergunta.")
            if not self.store.documents():
                turn.update(status="empty_base", answer="A base está vazia. Envie um material na aba Materiais e clique em Indexar materiais.")
                return turn
            query, hits = retrieve(question, history, self.embedder, self.store, settings.k, settings.min_similarity)
            turn["trace"].update(retrieval_query=query, embedding_profile=dict(self.embedder.profile))
            turn["sources"] = [{
                **hit.chunk.to_dict(), "retrieval_rank": hit.rank,
                "distance": hit.distance, "similarity": hit.similarity,
                "retrieved": True, "eligible": hit.eligible,
                "planned": False, "sent": False, "cited": False, "label": None,
                "excluded_reason": "abaixo do limiar" if not hit.eligible else None,
            } for hit in hits]
            if not any(hit.eligible for hit in hits):
                turn.update(status="no_relevant_content", answer="Nenhum trecho atingiu o limiar de busca configurado. Reformule a pergunta ou envie um material que trate do assunto; confira também os trechos recuperados. Esse resultado não prova que o assunto esteja ausente da base.")
                return turn
            router = self.router_factory(api_key)
            caps = router.capabilities(settings.model)
            plan = build_context(question, history, hits, caps, settings.max_tokens)
            turn["notices"].extend(plan.notices)
            if "temperature" not in caps.parameters:
                turn["notices"].append("Este modelo não anuncia suporte à temperatura; o parâmetro foi omitido nesta consulta.")
            turn["trace"].update(
                model_capabilities=asdict(caps), output_tokens_applied=plan.output_tokens,
                temperature_applied=settings.temperature if "temperature" in caps.parameters else None,
                estimated_input_units=plan.estimated_input, input_budget=plan.input_budget,
                estimation="bytes UTF-8 + overhead + margem; não é contagem exata do tokenizer da LLM",
                history_turns_sent=plan.history_turns_sent,
                planned_reference_map={label: hit.chunk.id for label, hit in plan.sent.items()},
                system_prompt_hash=digest(plan.messages[0]["content"]),
            )
            if not plan.sent:
                turn.update(status="context_too_small", answer="Os trechos recuperados não cabem integralmente na janela disponível. Escolha um modelo com contexto maior ou reduza o teto de saída.")
                return turn
            for source in turn["sources"]:
                source["label"] = next((label for label, hit in plan.sent.items() if hit.chunk.id == source["id"]), None)
                source["planned"] = source["label"] is not None
                if source["eligible"] and not source["planned"]:
                    source["excluded_reason"] = "fora do orçamento de contexto"
            turn["trace"]["request_messages"] = plan.messages
            turn["trace"]["delivery"] = "attempted_not_confirmed"
            completion = router.complete(caps, plan, settings.temperature)
            turn["trace"]["delivery"] = "completion_received"
            turn["reference_map"] = {label: hit.chunk.id for label, hit in plan.sent.items()}
            checked = validate_citations(completion["content"], set(plan.sent))
            turn.update(answer=checked.answer, status=checked.status)
            turn["trace"].update(
                raw_answer=completion["content"], invalid_citations=checked.invalid,
                llm_cited_labels=checked.cited,
                **{k: v for k, v in completion.items() if k != "content"},
            )
            for source in turn["sources"]:
                source["sent"] = source["planned"]
                source["cited"] = source["label"] in checked.cited
            if checked.warning:
                turn["notices"].append(checked.warning)
            if completion["finish_reason"] == "length":
                turn["notices"].append("A resposta atingiu o teto de tokens e pode estar incompleta. Para uma solução detalhada, aumente o teto e peça a solução novamente.")
        except TutorError as error:
            turn.update(status="error", answer=str(error))
        return turn
