"""ContractAgent - étapes 1 et 2 : lire un contrat et en extraire obligations et droits avec un LLM.

Usage :
    python extract.py samples/contrat_fictif.txt
    python extract.py mon_contrat.pdf
"""

import json
import os
import sys
import time
from pathlib import Path

import pdfplumber
from google import genai
from google.genai import errors, types

# Modèle disponible dans le niveau gratuit de Gemini (vérifie le nom dans Google AI Studio
# si une erreur "model not found" apparaît : les noms évoluent).
MODEL = "gemini-3.8-flash"
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
    # La clé API est lue dans la variable d'environnement GEMINI_API_KEY.
    # Elle n'est JAMAIS écrite dans le code (bonne pratique de sécurité).
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("Variable GEMINI_API_KEY absente. Fais : export GEMINI_API_KEY=\"ta_clé\"")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")

    # Les erreurs 5xx (ex : 503 "surcharge") sont temporaires : on réessaie
    # avec une attente de plus en plus longue (« exponential backoff »).
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=f"<contrat>\n{contract_text}\n</contrat>",
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,  # le prompt = les règles du jeu
                    temperature=0,  # on veut des réponses stables pour de l'extraction
                    response_mime_type="application/json",  # force une sortie JSON
                ),
            )
            break
        except errors.ServerError as err:
            if attempt == max_attempts:
                raise SystemExit(f"Serveur Gemini indisponible après {max_attempts} essais : {err}")
            wait = 5 * 2 ** (attempt - 1)  # 5 s, 10 s, 20 s, 40 s
            print(f"Serveur surchargé (essai {attempt}/{max_attempts}), nouvelle tentative dans {wait} s...")
            time.sleep(wait)

    raw = (response.text or "").strip()

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