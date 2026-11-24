"""Regenera o PDF de teste. Dependência adicional: pip install reportlab.

O PDF pronto já está incluído; este script não faz parte da execução do tutor.
"""

from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples" / "circuitos_logicos.pdf"
NAVY = colors.HexColor("#15324E")
BLUE = colors.HexColor("#2563EB")
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
if (FONT_DIR / "DejaVuSans.ttf").exists():
    pdfmetrics.registerFont(TTFont("FixtureSans", str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("FixtureBold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("FixtureMono", str(FONT_DIR / "DejaVuSansMono.ttf")))
    REGULAR, BOLD, MONO = "FixtureSans", "FixtureBold", "FixtureMono"
else:
    REGULAR, BOLD, MONO = "Helvetica", "Helvetica-Bold", "Courier-Bold"
styles = {
    "label": ParagraphStyle("label", fontName=BOLD, fontSize=9, leading=13, textColor=BLUE, spaceAfter=9),
    "title": ParagraphStyle("title", fontName=BOLD, fontSize=24, leading=29, textColor=NAVY, spaceAfter=16),
    "heading": ParagraphStyle("heading", fontName=BOLD, fontSize=14, leading=19, textColor=NAVY, spaceBefore=17, spaceAfter=9),
    "body": ParagraphStyle("body", fontName=REGULAR, fontSize=11, leading=17, textColor=NAVY, spaceAfter=10),
    "formula": ParagraphStyle("formula", fontName=MONO, fontSize=11, leading=18, textColor=BLUE, spaceBefore=3, spaceAfter=13),
}


def para(text, style="body"):
    return Paragraph(text, styles[style])


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#DAE4EF"))
    canvas.line(22 * mm, 22 * mm, A4[0] - 22 * mm, 22 * mm)
    canvas.setFont(REGULAR, 9)
    canvas.setFillColor(NAVY)
    canvas.drawString(22 * mm, 16 * mm, "TutorIA | Material original para teste")
    canvas.drawRightString(A4[0] - 22 * mm, 16 * mm, f"Página impressa {40 + doc.page}")
    canvas.restoreState()


def main():
    story = [
        para("CIRCUITOS LÓGICOS / 01", "label"),
        para("Teoremas de De Morgan", "title"),
        para("Texto didático original criado para verificar o TutorIA. Não é uma transcrição de livro, artigo ou aula."),
        para("Notação", "heading"),
        para("A e B são variáveis booleanas (0 ou 1). !A indica complemento; * indica AND; + indica OR."),
        para("As duas equivalências", "heading"),
        para("O complemento de uma soma lógica é o produto lógico dos complementos."),
        para("!(A + B) = !A * !B", "formula"),
        para("O complemento de um produto lógico é a soma lógica dos complementos."),
        para("!(A * B) = !A + !B", "formula"),
        para("Ao distribuir a negação, troque AND por OR (ou OR por AND) e complemente cada operando. A negação externa abrange toda a expressão entre parênteses."),
        para("Exemplo deste material", "heading"),
        para("Para A = 0 e B = 1: !(A+B) = !(0+1) = 0 e !A * !B = 1 * 0 = 0."),
    ]
    table = Table([["A", "B", "!(A+B)", "!A * !B"], ["0", "0", "1", "1"], ["0", "1", "0", "0"], ["1", "0", "0", "0"], ["1", "1", "0", "0"]], colWidths=[25*mm, 25*mm, 50*mm, 50*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), BOLD), ("FONTNAME", (0, 1), (-1, -1), REGULAR),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F0F5FA"), colors.white]),
    ]))
    story.extend([table, PageBreak(),
        para("CIRCUITOS LÓGICOS / 02", "label"),
        para("Estado e armazenamento", "title"),
        para("Combinacional e sequencial", "heading"),
        para("Um circuito combinacional tem saídas determinadas pelas entradas atuais e não armazena um estado interno para determinar essas saídas."),
        para("Um circuito sequencial armazena estado; suas saídas dependem do estado e, conforme o circuito, também das entradas atuais."),
        para("Latch D", "heading"),
        para("Um latch D com habilitação ativa em nível alto permite que Q acompanhe D enquanto a habilitação está em 1. Quando a habilitação está em 0, mantém o dado armazenado."),
        para("Flip-flop D", "heading"),
        para("Um flip-flop D acionado na borda de subida amostra D na transição de 0 para 1 do clock, respeitadas as condições de temporização, e mantém Q entre bordas ativas."),
        para("A diferença central é a sensibilidade a nível, no latch, e a borda, no flip-flop."),
        PageBreak(),
        para("CIRCUITOS LÓGICOS / 03", "label"),
        para("Exercício de simplificação", "title"),
        para("Enunciado", "heading"),
        para("Simplifique a função booleana a seguir:"),
        para("F = !(A + B) + !A * B", "formula"),
        para("Tentativa incorreta para discussão", "heading"),
        para("F = !A + !B + !A * B", "formula"),
        para("É preciso conferir a aplicação da negação externa ao primeiro termo."),
        para("Regras de apoio", "heading"),
        para("De Morgan: !(A + B) = !A * !B", "formula"),
        para("Distributividade: X*Y + X*Z = X*(Y+Z)", "formula"),
        para("Complementaridade: !B + B = 1", "formula"),
        para("Identidade: X * 1 = X", "formula"),
        para("Um caminho de resolução é substituir o primeiro termo por seu equivalente de De Morgan, colocar o fator comum em evidência e aplicar complementaridade e identidade. A solução final pode ser deduzida dessas regras."),
    ])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=22*mm, rightMargin=22*mm, topMargin=24*mm, bottomMargin=30*mm,
                                title="Circuitos Lógicos - material de teste", author="TutorIA - material original de teste")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    main()
