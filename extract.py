"""ContractAgent - étapes 1 et 2 : lire un contrat et en extraire obligations et droits avec un LLM.

Usage :
    python extract.py samples/contrat_fictif.txt
    python extract.py mon_contrat.pdf
"""

import json
import sys
from pathlib import Path

import pdfplumber
from anthropic import Anthropic

MODEL = "claude-sonnet-5-5"
PROMPT_FILE = Path(__file__).parent / "prompts" / "prompt_v1.txt"


def read_contract(path: Path) -> str:
    """ÉTAPE 1 : transformer le fichier (PDF ou texte) en texte brut."""
    if path.suffix.lower() == ".pdf":
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    return path.read_text(encoding="utf-8")


def extract_clauses(contract_text: str) -> dict:
    """ÉTAPE 2 : envoyer le texte à l'IA avec le prompt, récupérer du JSON."""
    # La clé API est lue dans la variable d'environnement ANTHROPIC_API_KEY.
    # Elle n'est JAMAIS écrite dans le code (bonne pratique de sécurité).
    client = Anthropic()
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        temperature=0,  # on veut des réponses stables pour de l'extraction
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"<contrat>\n{contract_text}\n</contrat>",
            }
        ],
    )
    raw = response.content[0].text.strip()

    # Au cas où le modèle ajoute des balises ```json malgré la consigne.
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.removeprefix("json").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise SystemExit(f"Le modèle n'a pas renvoyé un JSON valide : {err}\n---\n{raw}")


def print_table(data: dict) -> None:
    """Affichage simple dans le terminal (l'interface graphique viendra après)."""
    print("Parties :", ", ".join(data.get("parties", [])))
    print()
    print(f"{'TYPE':<11}{'PARTIE':<14}{'ÉCHÉANCE':<22}{'CLAUSE':<12}DESCRIPTION")
    print("-" * 100)
    for e in data.get("elements", []):
        print(
            f"{e.get('type') or '-':<11}"
            f"{(e.get('partie') or '-')[:13]:<14}"
            f"{(e.get('echeance') or '-')[:21]:<22}"
            f"{(e.get('clause') or '-')[:11]:<12}"
            f"{e.get('description') or '-'}"
        )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage : python extract.py <contrat.pdf|contrat.txt>")

    path = Path(sys.argv[1])
    if not path.exists():
        raise SystemExit(f"Fichier introuvable : {path}")

    text = read_contract(path)
    if not text.strip():
        raise SystemExit("Aucun texte extrait (PDF scanné ? il faudrait de l'OCR).")

    data = extract_clauses(text)
    print_table(data)

    # On sauvegarde aussi le résultat brut : utile pour comparer tes versions de prompt.
    out = path.with_suffix(".result.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRésultat sauvegardé dans {out}")


if __name__ == "__main__":
    main()