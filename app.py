"""ContractAgent - interface desktop (PySide6).

Lancer :  python app.py
La clé API doit être dans la variable d'environnement GEMINI_API_KEY.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from export_excel import HEADERS, export_to_excel
from extract import MODEL, PROMPT_FILE, ExtractionError, extract_clauses, format_alerts, read_contract

SUPPORTED_SUFFIXES = {".pdf", ".txt"}

# Colonnes du tableau : 0 = case « Validé », puis les champs du JSON dans cet ordre.
COL_VALID = 0
COL_DESCRIPTION = 3
FIELDS = ["type", "partie", "description", "echeance", "clause"]
COLUMN_WIDTHS = {0: 65, 1: 90, 2: 150, 4: 160, 5: 85}  # tout sauf la Description (colonne 3)
MIN_DESCRIPTION_WIDTH = 320

# Couleurs de lignes (fond ET texte définis ensemble, pour rester lisible en mode sombre).
ROW_COLORS = {
    "obligation": QColor("#FDE8D0"),
    "droit": QColor("#D9F2E0"),
}
TEXT_COLOR = QColor("#222222")


class ExtractionWorker(QThread):
    """Fait le travail long (lecture + appel à l'IA) dans un fil séparé.

    Si on appelait l'IA directement dans la fenêtre, l'interface serait gelée pendant
    toute la durée de l'appel (parfois plus d'une minute avec les nouvelles tentatives).
    Le fil communique avec la fenêtre uniquement par des « signaux ».
    """

    status = Signal(str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def run(self) -> None:
        try:
            self.status.emit("Lecture du contrat...")
            text = read_contract(self.path)
            if not text.strip():
                raise ExtractionError("Aucun texte extrait (PDF scanné ? il faudrait de l'OCR).")
            self.status.emit("Analyse par l'IA en cours (peut prendre un moment)...")
            data = extract_clauses(text, on_status=self.status.emit)
            self.finished_ok.emit(data)
        except ExtractionError as err:
            self.failed.emit(str(err))
        except Exception as err:  # filet de sécurité : l'interface ne doit jamais planter en silence
            self.failed.emit(f"Erreur inattendue ({type(err).__name__}) : {err}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ContractAgent - extraction d'obligations et de droits")
        # Taille adaptée à l'écran (sur un petit écran ou avec un zoom Windows, 1150 px peut dépasser).
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1150, int(screen.width() * 0.9)), min(680, int(screen.height() * 0.9)))
        self.setAcceptDrops(True)  # glisser-déposer d'un fichier dans la fenêtre

        self.worker = None
        self.current_path = None
        self.current_data = None

        # --- Barre du haut : boutons ---
        self.open_button = QPushButton("Charger un contrat...")
        self.export_button = QPushButton("Exporter en Excel...")
        self.export_button.setEnabled(False)
        self.open_button.clicked.connect(self.choose_file)
        self.export_button.clicked.connect(self.export_excel)

        buttons = QHBoxLayout()
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.export_button)
        buttons.addStretch()

        # --- Informations sur le contrat ---
        self.file_label = QLabel("Aucun contrat chargé. Clique sur « Charger » ou glisse un PDF / .txt dans la fenêtre.")
        self.parties_label = QLabel("")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # barre « indéterminée » : animation en continu
        self.progress.setVisible(False)

        # --- Tableau des résultats ---
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        # Largeurs fixes (modifiables à la souris) pour les petites colonnes ; la Description
        # prend TOUT l'espace restant. Avec « s'adapter au contenu », un long nom de partie
        # écrasait la description. Le texte long passe à la ligne au lieu d'élargir la colonne.
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(60)
        header.setStretchLastSection(False)
        for col, width in COLUMN_WIDTHS.items():
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col, width)
        # La Description est ajustée par fit_description() : tout l'espace restant, mais jamais
        # moins de MIN_DESCRIPTION_WIDTH (une barre de défilement apparaît si la fenêtre est trop étroite).
        header.setSectionResizeMode(COL_DESCRIPTION, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(COL_DESCRIPTION, MIN_DESCRIPTION_WIDTH)
        # Quand une colonne change de largeur (fenêtre redimensionnée...), la hauteur des lignes suit.
        header.sectionResized.connect(lambda *_: self.table.resizeRowsToContents())

        hint = QLabel(
            "Double-clique sur une cellule pour corriger le texte. "
            "Coche « Validé » quand tu as vérifié la ligne dans le contrat."
        )

        # --- Zone d'alertes (cachée tant qu'il n'y en a pas) ---
        self.alerts_title = QLabel("Alertes : texte suspect repéré dans le contrat")
        self.alerts_box = QPlainTextEdit()
        self.alerts_box.setReadOnly(True)
        self.alerts_box.setMaximumHeight(90)
        self.alerts_title.setVisible(False)
        self.alerts_box.setVisible(False)

        # --- Assemblage ---
        layout = QVBoxLayout()
        layout.addLayout(buttons)
        layout.addWidget(self.file_label)
        layout.addWidget(self.parties_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(hint)
        layout.addWidget(self.alerts_title)
        layout.addWidget(self.alerts_box)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.model_label = QLabel(f"Modèle : {MODEL} (+ secours)  |  Prompt : {PROMPT_FILE.name}")
        self.statusBar().addPermanentWidget(self.model_label)
        self.statusBar().showMessage("Prêt.")

    # ---------- Mise en page ----------

    def fit_description(self) -> None:
        """Donne à la Description tout l'espace que les autres colonnes laissent libre."""
        others = sum(self.table.columnWidth(c) for c in range(self.table.columnCount()) if c != COL_DESCRIPTION)
        available = self.table.viewport().width() - others
        self.table.setColumnWidth(COL_DESCRIPTION, max(MIN_DESCRIPTION_WIDTH, available))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # On attend que Qt ait fini de recalculer la taille du tableau avant de mesurer.
        QTimer.singleShot(0, self.fit_description)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.fit_description)

    # ---------- Chargement d'un contrat ----------

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir un contrat", "", "Contrats (*.pdf *.txt)")
        if path:
            self.load_contract(path)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.load_contract(urls[0].toLocalFile())

    def load_contract(self, path_str: str) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.statusBar().showMessage("Une analyse est déjà en cours, patiente un instant.")
            return
        path = Path(path_str)
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            QMessageBox.warning(self, "Format non pris en charge", "Choisis un fichier .pdf ou .txt.")
            return

        self.current_path = path
        self.file_label.setText(f"Contrat : {path.name}")
        self.set_busy(True)

        self.worker = ExtractionWorker(path)
        self.worker.status.connect(self.statusBar().showMessage)
        self.worker.finished_ok.connect(self.on_success)
        self.worker.failed.connect(self.on_failure)
        self.worker.start()

    def set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.open_button.setEnabled(not busy)
        self.export_button.setEnabled(not busy and self.current_data is not None)

    def on_success(self, data: dict) -> None:
        self.current_data = data
        self.show_results(data)
        self.set_busy(False)
        count = self.table.rowCount()
        used = data.get("modele_utilise", MODEL)
        self.model_label.setText(f"Modèle utilisé : {used}  |  Prompt : {PROMPT_FILE.name}")
        self.statusBar().showMessage(f"Terminé : {count} éléments extraits. Vérifie chaque ligne puis coche « Validé ».")

    def on_failure(self, message: str) -> None:
        self.set_busy(False)
        self.statusBar().showMessage("Échec de l'analyse.")
        QMessageBox.critical(self, "Échec de l'analyse", message)

    # ---------- Affichage des résultats ----------

    def show_results(self, data: dict) -> None:
        parties = [str(p) for p in data.get("parties") or []]
        self.parties_label.setText("Parties : " + (", ".join(parties) if parties else "non identifiées"))

        elements = [e for e in data.get("elements", []) if isinstance(e, dict)]
        self.table.setRowCount(len(elements))
        for row, element in enumerate(elements):
            kind = str(element.get("type") or "").strip().lower()
            background = QBrush(ROW_COLORS.get(kind, QColor("#EEEEEE")))

            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Unchecked)
            self._paint(check, background)
            self.table.setItem(row, COL_VALID, check)

            for col, key in enumerate(FIELDS, start=1):
                value = element.get(key)
                item = QTableWidgetItem("" if value is None else str(value))
                self._paint(item, background)
                self.table.setItem(row, col, item)
        self.table.resizeRowsToContents()

        alerts = format_alerts(data)
        self.alerts_box.setPlainText("\n".join(f"- {line}" for line in alerts))
        self.alerts_title.setVisible(bool(alerts))
        self.alerts_box.setVisible(bool(alerts))

    @staticmethod
    def _paint(item: QTableWidgetItem, background: QBrush) -> None:
        item.setBackground(background)
        item.setForeground(QBrush(TEXT_COLOR))

    # ---------- Export Excel ----------

    def table_rows(self) -> list:
        """Relit le tableau tel qu'il est affiché (donc avec tes corrections et tes validations)."""
        rows = []
        for row in range(self.table.rowCount()):
            valid = self.table.item(row, COL_VALID).checkState() == Qt.CheckState.Checked
            texts = []
            for col in range(1, len(HEADERS)):
                item = self.table.item(row, col)
                texts.append(item.text() if item else "")
            rows.append((valid, *texts))
        return rows

    def export_excel(self) -> None:
        if self.current_data is None or self.current_path is None:
            return
        default_name = f"{self.current_path.stem}_extraction.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en Excel", default_name, "Excel (*.xlsx)")
        if not path:
            return
        parties = [str(p) for p in self.current_data.get("parties") or []]
        try:
            export_to_excel(self.table_rows(), parties, format_alerts(self.current_data), self.current_path.name, path)
        except OSError as err:
            QMessageBox.warning(
                self,
                "Export impossible",
                f"Impossible d'écrire le fichier (est-il déjà ouvert dans Excel ?).\n\n{err}",
            )
            return
        self.statusBar().showMessage(f"Exporté : {path}")

    # ---------- Fermeture ----------

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.statusBar().showMessage("Analyse en cours : attends la fin avant de fermer.")
            event.ignore()
            return
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()