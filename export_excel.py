"""Export des résultats vers un fichier Excel (.xlsx) avec openpyxl."""

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADERS = ["Validé", "Type", "Partie", "Description", "Échéance / délai", "Clause"]
COLUMN_WIDTHS = [9, 13, 24, 60, 28, 14]


def _safe_write(sheet, row: int, column: int, value) -> None:
    """Écrit une valeur texte en garantissant qu'Excel ne l'interprétera jamais comme une formule.

    Sécurité : le texte vient d'un contrat et d'une IA, donc d'une source non fiable.
    openpyxl transforme tout texte qui commence par « = » en formule, ce qui permettrait
    à un contrat piégé de glisser une formule malveillante dans ton Excel
    (« injection de formule »). On force donc le type « texte ».
    """
    cell = sheet.cell(row=row, column=column, value=value)
    if isinstance(value, str):
        cell.data_type = "s"
    cell.alignment = Alignment(wrap_text=True, vertical="top")


def export_to_excel(rows, parties, alerts, source_name: str, path) -> None:
    """Crée le fichier Excel.

    rows : liste de tuples (valide: bool, type, partie, description, echeance, clause)
    parties : liste de noms de parties
    alerts : liste de phrases d'alerte
    """
    workbook = Workbook()

    # --- Feuille 1 : les éléments extraits ---
    sheet = workbook.active
    sheet.title = "Extraction"
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for col, title in enumerate(HEADERS, start=1):
        cell = sheet.cell(row=1, column=col, value=title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")

    for row_index, (valid, *texts) in enumerate(rows, start=2):
        _safe_write(sheet, row_index, 1, "Oui" if valid else "Non")
        for col_offset, text in enumerate(texts, start=2):
            _safe_write(sheet, row_index, col_offset, str(text))

    for col, width in enumerate(COLUMN_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(col)].width = width
    sheet.freeze_panes = "A2"  # l'en-tête reste visible quand on fait défiler
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{max(len(rows) + 1, 1)}"

    # --- Feuille 2 : informations générales et alertes ---
    info = workbook.create_sheet("Infos")
    info_rows = [
        ("Contrat source", source_name),
        ("Parties", ", ".join(str(p) for p in parties)),
        ("Date d'export", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("Éléments extraits", str(len(rows))),
        ("Éléments validés", str(sum(1 for r in rows if r[0]))),
    ]
    for row_index, (label, value) in enumerate(info_rows, start=1):
        info.cell(row=row_index, column=1, value=label).font = Font(bold=True)
        _safe_write(info, row_index, 2, value)

    next_row = len(info_rows) + 2
    info.cell(row=next_row, column=1, value="Alertes").font = Font(bold=True)
    if alerts:
        for offset, alert in enumerate(alerts):
            _safe_write(info, next_row + offset, 2, alert)
    else:
        _safe_write(info, next_row, 2, "Aucune")
    info.column_dimensions["A"].width = 20
    info.column_dimensions["B"].width = 90

    workbook.save(Path(path))