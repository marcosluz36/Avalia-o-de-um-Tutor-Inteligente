"""Planejamento conservador do contexto sem cortar chunks no meio."""

from pathlib import Path
import json
import re

from .types import ContextPlan, TutorError

SYSTEM_PROMPT = Path(__file__).with_name("prompts").joinpath("system.txt").read_text(encoding="utf-8")


def conservative_tokens(messages: list[dict[str, str]]) -> int:
    # Uma unidade por byte UTF-8 + overhead e margem. Deliberadamente muito
    # conservador para texto; não é a contagem exata do tokenizer do provedor.
    return 128 + sum(len(m["content"].encode("utf-8")) + 96 for m in messages)


def reference_message(sent: dict) -> dict[str, str]:
    chunks = []
    for label, hit in sent.items():
        c = hit.chunk
        m = c.metadata
        chunks.append({
            "reference": f"[{label}]", "chunk_id": c.id,
            "filename": m.get("filename"), "material_title": m.get("material_title"),
            "section": m.get("section"), "pdf_pages": m.get("pdf_pages", []),
            "slides": m.get("slides", []), "printed_pages": m.get("printed_pages", []),
            "pdf_page_labels": m.get("pdf_page_labels", []),
            "text_with_headings": c.contextualized_text,
        })
    content = json.dumps({"kind": "reference_material_only", "chunks": chunks}, ensure_ascii=False)
    return {"role": "user", "content": content}


def build_context(question: str, history: list[dict], hits: list, caps,
                  requested_output: int) -> ContextPlan:
    if caps.context_length <= 0:
        raise TutorError("A janela de contexto do modelo não foi informada pelo catálogo.")
    output = min(requested_output, caps.max_completion_tokens or requested_output)
    margin = max(256, min(1024, caps.context_length // 10))
    budget = caps.context_length - output - margin
    system = {"role": "system", "content": SYSTEM_PROMPT}
    current = {"role": "user", "content": question}
    notices = []
    if output != requested_output:
        notices.append(f"O teto de saída foi ajustado de {requested_output} para {output} tokens conforme o catálogo.")

    def messages(pairs, sources):
        return [system, *pairs, reference_message(sources), current]

    if conservative_tokens(messages([], {})) > budget:
        raise TutorError("A pergunta, as regras e a reserva de saída excedem a janela do modelo. Encurte a pergunta, reduza o teto de saída ou escolha um modelo com janela maior.")
    kept, kept_turns = [], 0
    available = budget - conservative_tokens(messages([], {}))
    # Reserva até 1/3 do espaço livre ao histórico; adiciona pares inteiros.
    for turn in reversed(history[-6:]):
        answer = re.sub(r"\[C\d+\]", "", turn["answer"])
        old_question = re.sub(r"\[C\d+\]", "", turn["question"])
        pair = [{"role": "user", "content": old_question}, {"role": "assistant", "content": answer}]
        if conservative_tokens(pair + kept) > available // 3:
            break
        kept = pair + kept
        kept_turns += 1
    sent = {}
    for hit in hits:
        if not hit.eligible:
            continue
        label = f"C{len(sent) + 1}"
        proposed = {**sent, label: hit}
        if conservative_tokens(messages(kept, proposed)) <= budget:
            sent = proposed
    if not sent:
        # Um trecho tem prioridade sobre histórico quando a janela é curta.
        for hit in hits:
            if hit.eligible and conservative_tokens(messages([], {"C1": hit})) <= budget:
                sent, kept, kept_turns = {"C1": hit}, [], 0
                break
    if kept_turns < len(history):
        notices.append(f"Histórico enviado: {kept_turns} de {len(history)} turnos; o histórico completo continua na interface.")
    eligible_count = sum(h.eligible for h in hits)
    if len(sent) < eligible_count:
        notices.append(f"{eligible_count - len(sent)} chunk(s) acima do limiar ficaram fora da janela; os trechos enviados estão integrais.")
    final_messages = messages(kept, sent)
    return ContextPlan(final_messages, sent, conservative_tokens(final_messages), budget, output, kept_turns, notices)
