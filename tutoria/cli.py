"""Execute python -m tutoria.cli --help."""

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

from .config import Settings
from .types import QuerySettings, TutorError
from .util import read_json


def backend(settings):
    from .embeddings import E5Embedder
    from .store import VectorStore

    embedder = E5Embedder(settings)
    return embedder, VectorStore(settings.data_dir, embedder.profile)


def parser():
    cli = argparse.ArgumentParser(description="TutorIA local: indexação, consulta e rastreabilidade.")
    commands = cli.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="Indexar arquivos locais; arquivos idênticos são reaproveitados.")
    index.add_argument("files", type=Path, nargs="+")
    index.add_argument("--force", action="store_true", help="Refazer explicitamente extração, chunks e vetores.")
    index.add_argument("--ocr", action="store_true", help="Habilitar OCR pt/en para PDF (requer requirements-ocr.txt).")
    index.add_argument("--formulas", action="store_true", help="Habilitar enriquecimento local de fórmulas (mais pesado).")
    index.add_argument("--title", help="Título declarado pelo usuário; use com um único arquivo.")
    index.add_argument("--page-map", type=Path, help='JSON com mapa declarado, por exemplo {"2":"1"}; um PDF.')
    commands.add_parser("list", help="Listar documentos e IDs sem carregar modelos.")
    chunk = commands.add_parser("chunk", help="Exibir chunk integral, metadados e origem.")
    chunk.add_argument("id")
    remove = commands.add_parser("remove", help="Remover documento da busca; originais e caches são preservados.")
    remove.add_argument("document_id")
    commands.add_parser("models", help="Listar IDs de modelos do catálogo atual do OpenRouter.")
    ask = commands.add_parser("ask", help="Uma consulta sem histórico (para conversar, use a interface).")
    ask.add_argument("question")
    ask.add_argument("--model", default=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
    ask.add_argument("--temperature", type=float, default=0.2)
    ask.add_argument("--k", type=int, default=4)
    ask.add_argument("--max-tokens", type=int, default=300)
    ask.add_argument("--min-similarity", type=float, default=0.75)
    ask.add_argument("--json", action="store_true", help="Emitir resposta e trilha completa; não inclui chave de API.")
    return cli


def main() -> int:
    try:
        settings = Settings.from_env()
        args = parser().parse_args()
        if args.command == "list":
            print(json.dumps(read_json(settings.data_dir / "manifest.json", {"documents": {}})["documents"], ensure_ascii=False, indent=2))
            return 0
        if args.command == "models":
            from .openrouter import OpenRouter

            for model in OpenRouter(os.getenv("OPENROUTER_API_KEY", "")).models():
                print(model["id"])
            return 0
        if args.command == "index":
            from .indexing import index_document

            if len(args.files) != 1 and (args.title or args.page_map):
                raise TutorError("Use --title e --page-map com um único arquivo por comando.")
            settings = replace(settings, ocr=args.ocr or settings.ocr, formulas=args.formulas or settings.formulas)
            page_map = read_json(args.page_map) if args.page_map else None
            if args.page_map and not isinstance(page_map, dict):
                raise TutorError("O arquivo de mapeamento precisa existir e conter um objeto JSON.")
            embedder, store = backend(settings)
            failed = False
            for path in args.files:
                try:
                    result = index_document(path.read_bytes(), path.name, settings, embedder, store,
                                            args.force, args.title, page_map, lambda msg: print(msg, file=sys.stderr))
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                except (TutorError, OSError) as error:
                    print(f"Falha em {path.name}: {error if isinstance(error, TutorError) else 'não foi possível ler/gravar o arquivo.'}", file=sys.stderr)
                    failed = True
            return 1 if failed else 0
        if args.command in {"chunk", "remove"}:
            # Operações de leitura/remoção não exigem download/carregamento do E5.
            from .store import VectorStore

            profile = read_json(settings.data_dir / "embedding_profile.json")
            if not profile:
                raise TutorError("A base está vazia. Indexe um material primeiro.")
            store = VectorStore(settings.data_dir, profile)
            if args.command == "chunk":
                print(json.dumps(store.get_chunk(args.id).to_dict(), ensure_ascii=False, indent=2))
            else:
                store.remove(args.document_id)
                print("Documento removido da busca. Originais e cache preservados.")
            return 0
        from .tutor import Tutor

        if not read_json(settings.data_dir / "manifest.json", {"documents": {}})["documents"]:
            raise TutorError("A base está vazia. Use o comando index antes de ask.")
        embedder, store = backend(settings)
        query_settings = QuerySettings(args.model, args.temperature, args.k, args.max_tokens, args.min_similarity)
        turn = Tutor(embedder, store).ask(args.question, [], query_settings, os.getenv("OPENROUTER_API_KEY", ""))
        if args.json:
            print(json.dumps(turn, ensure_ascii=False, indent=2))
        else:
            print(turn["answer"])
            for notice in turn["notices"]:
                print("Aviso: " + notice)
            for label, chunk_id in turn["reference_map"].items():
                print(f"[{label}] {chunk_id}")
        return 1 if turn["status"] in {"error", "citation_error", "context_too_small"} else 0
    except TutorError as error:
        print(str(error), file=sys.stderr)
    except ImportError:
        print("Dependências ausentes ou incompatíveis. Execute pip install -r requirements.txt.", file=sys.stderr)
    except Exception as error:
        # Não imprime traceback nem conteúdo de exceções de terceiros.
        print(f"Falha local ({type(error).__name__}). Confira arquivos, instalação e permissões da pasta de dados.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
