"""Extração Docling com cache independente do chunking e dos embeddings."""

from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .types import TutorError
from .util import atomic_json, digest, package_version, read_json


@dataclass
class Extraction:
    document: object
    metadata: dict
    warnings: list[str]


def extraction_profile(settings: Settings) -> dict:
    return {
        "schema": 1, "docling": package_version("docling"),
        "docling_core": package_version("docling-core"),
        "ocr": settings.ocr, "ocr_languages": ["pt", "en"] if settings.ocr else [],
        "formulas": settings.formulas, "tables": True,
    }


def extract(source: Path, doc_id: str, settings: Settings, force: bool = False) -> Extraction:
    from docling_core.types.doc import DoclingDocument

    profile = extraction_profile(settings)
    directory = settings.data_dir / "extractions" / doc_id / digest(profile)
    completion = directory / "extraction.json"
    if completion.exists() and not force:
        cached = read_json(completion)
        try:
            document = DoclingDocument.model_validate(read_json(directory / "docling.json"))
        except Exception:
            raise TutorError("Cache de extração inválido. Use a opção de reprocessamento explícito.") from None
        return Extraction(document, cached["metadata"], cached["warnings"])

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = settings.ocr
    options.do_table_structure = True
    options.do_formula_enrichment = settings.formulas
    options.do_picture_description = False
    if settings.ocr:
        options.ocr_options = EasyOcrOptions(lang=["pt", "en"], use_gpu=False)
    try:
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF, InputFormat.DOCX, InputFormat.PPTX, InputFormat.MD],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
        )
        result = converter.convert(source=source, raises_on_error=False)
        status = getattr(result.status, "value", str(result.status))
        if status != "success":
            raise TutorError("O Docling não concluiu a extração integral. Confira o arquivo, a instalação e os modelos locais; PDFs digitalizados podem precisar de OCR. O documento não foi indexado.")
        document = result.document
        markdown = document.export_to_markdown()
    except TutorError:
        raise
    except Exception:
        raise TutorError("Falha de extração no Docling. Confira o formato, a instalação, os modelos baixados e a opção de OCR. O documento não foi indexado.") from None

    text_items = [i for i in getattr(document, "texts", []) if getattr(i, "text", "").strip()]
    table_text = [getattr(cell, "text", "").strip()
                  for table in getattr(document, "tables", [])
                  for cell in getattr(getattr(table, "data", None), "table_cells", [])]
    if not text_items and not any(table_text):
        raise TutorError("Nenhum texto foi extraído. Se o PDF for uma digitalização, habilite OCR e reindexe; diagramas isolados precisam de descrição textual.")
    titles = [i.text.strip() for i in text_items if str(getattr(i.label, "value", i.label)) == "title"]
    metadata = {
        "material_title": titles[0] if titles else None,
        "title_origin": "docling_title" if titles else None,
        "format": source.suffix.lower().lstrip("."),
        "source_path": str(source.relative_to(settings.data_dir)),
        "extracted_markdown_path": str((directory / "material.md").relative_to(settings.data_dir)),
        "docling_json_path": str((directory / "docling.json").relative_to(settings.data_dir)),
        "extraction_profile": profile,
        "pdf_page_count": None, "pdf_page_labels": {},
    }
    warnings = ["Fórmulas, barras de negação, tabelas e diagramas podem conter perdas de extração. Confira o original antes de usar uma notação ambígua."]
    if not settings.formulas:
        warnings.append("Enriquecimento de fórmulas desativado; fórmulas em imagem podem não ser recuperadas.")
    if getattr(document, "pictures", []):
        warnings.append("Há figuras no documento. A aplicação não interpreta visualmente circuitos ou diagramas; apenas texto e legendas extraídos entram na busca.")
    if source.suffix.lower() == ".pdf":
        if not settings.ocr:
            warnings.append("OCR desativado. Texto presente apenas em imagens não será reconhecido.")
        try:
            from pypdf import PdfReader

            reader = PdfReader(source)
            metadata["pdf_page_count"] = len(reader.pages)
            if not titles and reader.metadata and reader.metadata.title:
                metadata["material_title"] = str(reader.metadata.title)
                metadata["title_origin"] = "pdf_metadata"
            # pypdf gera números sequenciais se /PageLabels estiver ausente.
            # Só armazenamos rótulos realmente declarados no arquivo.
            if "/PageLabels" in reader.trailer["/Root"]:
                metadata["pdf_page_labels"] = {str(n): label for n, label in enumerate(reader.page_labels, 1)}
            pages_with_text = {p.page_no for item in text_items for p in getattr(item, "prov", [])}
            pages_with_text.update(p.page_no for item in getattr(document, "tables", []) for p in getattr(item, "prov", []))
            missing = sorted(set(range(1, len(reader.pages) + 1)) - pages_with_text)
            if missing:
                metadata["pdf_pages_without_text"] = missing
                warnings.append("Páginas do PDF sem texto/tabela estruturada: " + ", ".join(map(str, missing)) + ". Podem ser páginas em branco ou conteúdo não extraído.")
        except Exception:
            warnings.append("Não foi possível ler metadados adicionais do PDF. Não inferimos numeração impressa.")

    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / "docling.json", document.model_dump(mode="json", by_alias=True))
    (directory / "material.md").write_text(markdown, encoding="utf-8")
    atomic_json(completion, {"metadata": metadata, "warnings": warnings})
    return Extraction(document, metadata, warnings)
