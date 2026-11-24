"""Interface local. Execute: streamlit run app.py"""

from dataclasses import replace
import json
import os
from pathlib import Path

import streamlit as st

from tutoria.config import Settings
from tutoria.indexing import index_document
from tutoria.tutor import Tutor, new_turn
from tutoria.types import QuerySettings, TutorError
from tutoria.util import artifact_path, read_json

# Rótulos curtos da interface e identificadores reais do OpenRouter.
MODEL_OPTIONS = {
    "gpt-4o-mini": "openai/gpt-4o-mini",
    "gemini-flash": "google/gemini-2.5-flash",
    "mistral": "mistralai/mistral-small-3.2-24b-instruct",
    "deepseek": "deepseek/deepseek-chat-v3-0324",
}

st.set_page_config(page_title="TutorIA · Circuitos Lógicos", page_icon="📘", layout="centered")


@st.cache_resource(show_spinner=False)
def get_backend(root: str, revision: str, batch_size: int):
    from tutoria.cli import backend

    return backend(Settings(Path(root), embedding_revision=revision, embedding_batch_size=batch_size))


def safe_failure(error: Exception) -> str:
    if isinstance(error, TutorError):
        return str(error)
    if isinstance(error, ImportError):
        return "Dependências ausentes ou incompatíveis. Execute pip install -r requirements.txt no ambiente virtual."
    return f"Falha local ({type(error).__name__}). Confira instalação, memória e permissões da pasta de dados."


def render_sources(turn: dict, root: Path):
    sources = turn["sources"]
    if not sources:
        return
    with st.expander(f"Fontes desta resposta · {len(sources)} recuperadas"):
        sent = sum(s["sent"] for s in sources)
        cited = sum(s["cited"] for s in sources)
        st.write(f"Recuperados: {len(sources)} · Enviados com resposta confirmada: {sent} · Citados pela LLM: {cited}")
        st.caption("Métrica: distância cosseno (menor é mais próximo). Similaridade = 1 − distância (maior é mais próximo). Esses valores não são probabilidades de acerto. Envio não comprova uso; citar não comprova sustentação semântica.")
        if turn["status"] == "citation_error":
            st.warning("A saída foi descartada. As marcações de citação abaixo descrevem a saída recebida da LLM, não uma resposta validada.")
        if turn["trace"].get("delivery") == "attempted_not_confirmed":
            st.info("O contexto foi preparado para uma chamada sem resposta confirmada. O recebimento pela LLM não pôde ser confirmado.")
        for source in sources:
            label = f"[{source['label']}]" if source["label"] else f"Recuperado #{source['retrieval_rank']}"
            metadata = source["metadata"]
            states = " · ".join([
                "recuperado", "enviado" if source["sent"] else ("preparado" if source["planned"] else "não enviado"),
                "citado pela LLM" if source["cited"] else "não citado",
            ])
            with st.container(border=True):
                st.write(f"{label} {metadata['filename']} · {states}")
                st.code(source["id"], language=None)
                st.write(f"Distância: {source['distance']:.4f} · Similaridade: {source['similarity']:.4f}")
                if source["excluded_reason"]:
                    st.caption(source["excluded_reason"])
                st.write("Texto integral do chunk")
                st.text(source["text"])
                if source["sent"] or source["planned"]:
                    st.write("Texto com títulos preparado para a LLM")
                    st.text(source["contextualized_text"])
                st.write("Metadados e localização no original")
                st.json(metadata, expanded=False)
                if metadata.get("pdf_pages"):
                    st.caption("Páginas do arquivo PDF, contando a primeira como 1: " + ", ".join(map(str, metadata["pdf_pages"])))
                elif metadata.get("slides"):
                    st.caption("Slides informados pela proveniência do Docling: " + ", ".join(map(str, metadata["slides"])))
                else:
                    st.caption("Página/slide não disponível na extração; use seção e referências de itens.")
                if not metadata.get("printed_pages"):
                    st.caption("Numeração impressa não mapeada. Rótulos internos do PDF, se presentes, não foram equiparados à numeração impressa.")
        # Uma cópia por documento, carregada apenas por ação explícita do usuário.
        documents = {s["metadata"]["document_id"]: s["metadata"] for s in sources}
        for doc_id, metadata in documents.items():
            if st.checkbox(f"Carregar original: {metadata['filename']}", key=f"load-{turn['id']}-{doc_id}"):
                try:
                    path = artifact_path(root, metadata["source_path"])
                    st.download_button("Baixar arquivo original", path.read_bytes(), file_name=metadata["filename"], key=f"original-{turn['id']}-{doc_id}")
                    extracted = artifact_path(root, metadata["extracted_markdown_path"])
                    st.download_button("Baixar texto extraído", extracted.read_bytes(), file_name=Path(metadata["filename"]).stem + "_extraido.md", key=f"extract-{turn['id']}-{doc_id}")
                except (OSError, TutorError):
                    st.info("O arquivo não está disponível nesta pasta. O texto e os metadados do chunk continuam preservados na resposta.")
        if st.checkbox("Exibir registro da consulta", key=f"trace-{turn['id']}"):
            st.json({"settings": turn["settings"], "reference_map": turn["reference_map"], "trace": turn["trace"]}, expanded=False)


def main():
    try:
        config = Settings.from_env()
    except Exception as error:
        st.error(safe_failure(error))
        return
    st.session_state.setdefault("turns", [])
    with st.sidebar:
        st.title("Configurações")
        password = st.text_input("Chave OpenRouter (opcional se definida no ambiente)", type="password", key="openrouter_key")
        api_key = password or os.getenv("OPENROUTER_API_KEY", "")
        model_ids = list(MODEL_OPTIONS.values())
        default_model = os.getenv("OPENROUTER_MODEL", model_ids[0])
        model = st.selectbox(
            "Modelo da LLM", options=model_ids,
            index=model_ids.index(default_model) if default_model in model_ids else 0,
            format_func=lambda model_id: next(
                label for label, identifier in MODEL_OPTIONS.items() if identifier == model_id
            ),
            key="selected_model",
        )
        temperature = st.slider("Temperatura", 0.0, 1.0, 0.2, 0.05)
        k = st.slider("Máximo de chunks recuperados (k)", 1, 20, 4)
        max_tokens = st.number_input("Teto de tokens de saída", min_value=32, max_value=16384, value=300, step=50)
        with st.expander("Ajustar busca"):
            threshold = st.slider("Similaridade cosseno mínima", -1.0, 1.0, 0.75, 0.01)
            st.caption("Limiar heurístico, sem calibração para seus materiais. Reduza-o se a busca excluir trechos úteis; isso pode incluir mais trechos irrelevantes.")
        st.caption("As alterações valem para novas consultas. O histórico e suas fontes são preservados.")
        st.caption("Embeddings locais. A pergunta, os trechos selecionados e parte do histórico são enviados ao OpenRouter para responder.")
        if st.session_state.turns:
            st.download_button("Exportar conversa e fontes", json.dumps(st.session_state.turns, ensure_ascii=False, indent=2), file_name="tutoria_conversa.json", mime="application/json")
            if st.button("Iniciar nova conversa"):
                st.session_state.turns = []
                st.rerun()

    query_settings = QuerySettings(model.strip(), temperature, k, int(max_tokens), threshold)
    st.title("TutorIA")
    st.caption("Circuitos Lógicos · Estude com explicações curtas, pistas e fontes verificáveis.")
    chat_tab, materials_tab = st.tabs(["Chat", "Materiais"])
    with materials_tab:
        uploads = st.file_uploader("Livros, slides e artigos", type=["pdf", "docx", "pptx", "md"], accept_multiple_files=True)
        st.caption("Formatos implementados: PDF, DOCX, PPTX e Markdown. Máximo de 100 MB por arquivo.")
        ocr = st.checkbox("Usar OCR em PDFs digitalizados (pt/en)", value=config.ocr)
        formulas = st.checkbox("Reconhecer fórmulas em imagens (mais lento)", value=config.formulas)
        title = st.text_input("Título do material (opcional; para um único arquivo)")
        force = st.checkbox("Reprocessar extração e índice dos arquivos selecionados", value=False)
        st.caption("Fórmulas, tabelas e diagramas exigem conferência no original. Figuras não recebem interpretação visual nesta versão.")
        if st.button("Indexar materiais", disabled=not uploads, type="primary"):
            if title.strip() and len(uploads) != 1:
                st.error("Informe um título apenas ao indexar um único arquivo.")
            else:
                results = []
                with st.status("Preparando a indexação…", expanded=True) as status:
                    try:
                        embedder, store = get_backend(str(config.data_dir), config.embedding_revision, config.embedding_batch_size)
                        ingestion_config = replace(config, ocr=ocr, formulas=formulas)
                        for upload in uploads:
                            try:
                                st.write(upload.name)
                                result = index_document(upload.getvalue(), upload.name, ingestion_config, embedder, store, force, title.strip() or None, progress=st.write)
                                results.append(result)
                            except Exception as error:
                                results.append({"filename": upload.name, "error": safe_failure(error)})
                        status.update(label="Indexação finalizada; confira os resultados.", state="complete")
                    except Exception as error:
                        status.update(label="Não foi possível iniciar a indexação.", state="error")
                        results.append({"error": safe_failure(error)})
                st.session_state["index_results"] = results
        for result in st.session_state.get("index_results", []):
            if "error" in result:
                st.error(result["error"])
            else:
                state = "Já indexado; reaproveitado" if result["status"] == "already_indexed" else "Indexado"
                st.success(f"{result['filename']}: {state} · {result['chunk_count']} chunks")
                for warning in result.get("warnings", []):
                    st.warning(warning)
        try:
            documents = read_json(config.data_dir / "manifest.json", {"documents": {}})["documents"]
            st.write(f"Base atual: {len(documents)} materiais · {sum(d['chunk_count'] for d in documents.values())} chunks")
            for doc in documents.values():
                with st.expander(doc["filename"]):
                    st.json(doc, expanded=False)
        except TutorError as error:
            st.error(str(error))

    with chat_tab:
        for turn in st.session_state.turns:
            with st.chat_message("user"):
                st.markdown(turn["question"])
            with st.chat_message("assistant"):
                st.markdown(turn["answer"])
                for notice in turn["notices"]:
                    st.caption(notice)
                render_sources(turn, config.data_dir)
    # No corpo principal: o Streamlit fixa a entrada no rodapé, inclusive ao rolar.
    question = st.chat_input("Pergunte sobre o material ou apresente sua tentativa…", key="chat_question")
    if question:
        with st.spinner("Consultando os materiais…"):
            try:
                if not read_json(config.data_dir / "manifest.json", {"documents": {}})["documents"]:
                    turn = new_turn(question, query_settings)
                    turn.update(status="empty_base", answer="A base está vazia. Envie um material na aba Materiais e clique em Indexar materiais.")
                else:
                    embedder, store = get_backend(str(config.data_dir), config.embedding_revision, config.embedding_batch_size)
                    history = [{"question": t["question"], "answer": t["answer"]} for t in st.session_state.turns if t["status"] in {"answered", "insufficient_support"}]
                    turn = Tutor(embedder, store).ask(question, history, query_settings, api_key)
            except Exception as error:
                turn = new_turn(question, query_settings)
                turn.update(status="error", answer=safe_failure(error))
            st.session_state.turns.append(turn)
        st.rerun()


if __name__ == "__main__":
    main()
