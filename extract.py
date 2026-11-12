"""ContractAgent - cœur du programme : lire un contrat et en extraire obligations et droits.

Ce fichier est utilisé de deux façons :
  - en ligne de commande :  python extract.py samples/contrat_fictif.txt
  - par l'interface graphique :  python app.py

Réglages possibles par variables d'environnement (aucun n'est obligatoire) :
    GEMINI_API_KEY   ta clé API (obligatoire)
    GEMINI_MODEL     un modèle à essayer EN PREMIER (puis la liste par défaut en secours)
    GEMINI_MODELS    liste IMPOSÉE de modèles séparés par des virgules (l'emporte sur GEMINI_MODEL).
                     Un seul nom = pas de bascule : idéal pour comparer des prompts.
    CONTRACT_PROMPT  le fichier de prompt à utiliser, ex : prompt_v2.txt
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import pdfplumber
from google import genai
from google.genai import errors, types

# Modèles essayés dans l'ordre. Si l'un est saturé ou retiré, on passe au suivant.
# (Les noms évoluent : lance python list_models.py pour voir ceux de ta clé.)
DEFAULT_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
]


def _model_chain() -> list:
    # Liste imposée : elle l'emporte sur tout le reste et rien n'y est ajouté. C'est ce qu'il faut
    # pour comparer proprement (un export GEMINI_MODEL oublié dans le terminal ne peut pas la fausser).
    explicit = [m.strip() for m in os.environ.get("GEMINI_MODELS", "").split(",") if m.strip()]
    if explicit:
        return explicit
    chain = list(DEFAULT_MODELS)
    chosen = os.environ.get("GEMINI_MODEL", "").strip()
    if chosen:
        chain = [chosen] + [m for m in chain if m != chosen]
    return chain


MODELS = _model_chain()
MODEL = MODELS[0]  # modèle essayé en premier (affiché dans l'interface)
PROMPT_FILE = Path(__file__).parent / "prompts" / os.environ.get("CONTRACT_PROMPT", "prompt_v1.txt")

ATTEMPTS_PER_MODEL = 3  # essais par modèle avant de passer au suivant
SKIP_MODEL_CODES = {404, 429}  # modèle retiré (404) ou quota atteint (429) : on tente un autre modèle

# Erreurs réseau temporaires (connexion coupée, délai dépassé...) : on peut réessayer.
NETWORK_ERRORS = {
    "ReadError",
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteError",
    "RemoteProtocolError",
}


class ExtractionError(Exception):
    """Erreur « attendue » (clé absente, serveur saturé, JSON invalide...).

    Le message est écrit pour être lu par l'utilisateur, tel quel.
    On utilise une exception plutôt que SystemExit pour que l'interface graphique
    puisse l'afficher dans une fenêtre au lieu de fermer le programme.
    """


class ModelUnavailable(Exception):
    """Ce modèle ne peut pas répondre pour le moment : on passe au suivant de la liste."""

    def __init__(self, model: str, original: Exception):
        super().__init__(f"{model} indisponible ({type(original).__name__})")
        self.model = model
        self.original = original


def read_contract(path: Path) -> str:
    """ÉTAPE 1 : transformer le fichier (PDF ou texte) en texte brut."""
    if path.suffix.lower() == ".pdf":
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    return path.read_text(encoding="utf-8")


def _call_model(client, model: str, system_prompt: str, contract_text: str, on_status: Callable[[str], None]):
    """Interroge UN modèle, avec quelques nouvelles tentatives si le problème est temporaire."""
    for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=f"<contrat>\n{contract_text}\n</contrat>",
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,  # le prompt = les règles du jeu
                    temperature=0,  # on veut des réponses stables pour de l'extraction
                    response_mime_type="application/json",  # force une sortie JSON
                ),
            )
        except errors.ClientError as err:
            # 4xx : le problème vient de la requête. Pour certains codes (modèle retiré, quota),
            # un AUTRE modèle peut marcher ; pour les autres (clé fausse...), inutile d'insister.
            code = getattr(err, "code", None)
            if code in SKIP_MODEL_CODES:
                raise ModelUnavailable(model, err) from err
            message = getattr(err, "message", None) or str(err)
            raise ExtractionError(f"Erreur de l'API Gemini ({code}) : {message}") from err
        except Exception as err:
            temporaire = isinstance(err, errors.ServerError) or type(err).__name__ in NETWORK_ERRORS
            if not temporaire:
                raise
            if attempt == ATTEMPTS_PER_MODEL:
                raise ModelUnavailable(model, err) from err
            wait = 3 * 2 ** (attempt - 1)  # 3 s, 6 s
            on_status(
                f"{model} : problème temporaire ({type(err).__name__}), "
                f"essai {attempt}/{ATTEMPTS_PER_MODEL}, nouvelle tentative dans {wait} s..."
            )
            time.sleep(wait)


def extract_clauses(contract_text: str, on_status: Optional[Callable[[str], None]] = None) -> dict:
    """ÉTAPE 2 : envoyer le texte à l'IA avec le prompt, récupérer du JSON.

    on_status : fonction appelée avec un message de progression (print par défaut,
    la barre d'état dans l'interface graphique).
    """
    if on_status is None:
        on_status = lambda message: print(message, flush=True)  # noqa: E731

    # La clé API est lue dans la variable d'environnement GEMINI_API_KEY.
    # Elle n'est JAMAIS écrite dans le code (bonne pratique de sécurité).
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ExtractionError('Variable GEMINI_API_KEY absente. Fais : export GEMINI_API_KEY="ta_clé"')
    client = genai.Client(api_key=api_key)
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")

    # On essaie les modèles l'un après l'autre jusqu'à ce que l'un réponde.
    last_problem = None
    for index, model in enumerate(MODELS):
        try:
            response = _call_model(client, model, system_prompt, contract_text, on_status)
            used_model = model
            break
        except ModelUnavailable as unavailable:
            last_problem = unavailable
            if index < len(MODELS) - 1:
                on_status(f"{unavailable} - essai du modèle suivant : {MODELS[index + 1]}...")
    else:
        if last_problem is not None and type(last_problem.original).__name__ in NETWORK_ERRORS:
            conseil = "Vérifie ta connexion, ton VPN ou ton antivirus, puis relance."
        else:
            conseil = (
                "Les serveurs Google sont surchargés ou ces modèles ne sont plus disponibles. "
                "Réessaie dans quelques minutes, ou vérifie les noms avec python list_models.py."
            )
        raise ExtractionError(f"Aucun des modèles testés n'a répondu ({', '.join(MODELS)}). {conseil}")

    raw = (response.text or "").strip()

    # Au cas où le modèle ajoute des balises ```json malgré la consigne.
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.removeprefix("json").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as err:
        raise ExtractionError(f"Le modèle n'a pas renvoyé un JSON valide : {err}\n---\n{raw[:500]}") from err

    # On ne fait jamais confiance à la sortie d'une IA : on vérifie la forme attendue.
    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        raise ExtractionError(f"Le JSON reçu n'a pas la structure attendue :\n{raw[:500]}")

    data["modele_utilise"] = used_model  # utile pour ton journal de prompt : un même prompt varie selon le modèle
    return data


def format_alerts(data: dict) -> list:
    """Renvoie les alertes (texte suspect repéré par l'IA) sous forme de liste de phrases.

    Fonctionne avec une liste de textes ou une liste d'objets, au choix de ton prompt.
    Sans champ « alertes » (prompt_v1), la liste est vide.
    """
    alerts = data.get("alertes") or []
    if not isinstance(alerts, list):
        alerts = [alerts]
    lines = []
    for alert in alerts:
        if isinstance(alert, dict):
            alert = " - ".join(str(value) for value in alert.values() if value)
        if str(alert).strip():
            lines.append(str(alert).strip())
    return lines


def print_table(data: dict) -> None:
    """Affichage simple dans le terminal."""
    parties = [str(p) for p in data.get("parties") or []]
    print("Parties :", ", ".join(parties))
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
    alerts = format_alerts(data)
    if alerts:
        print("\nALERTES :")
        for line in alerts:
            print(" !", line)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage : python extract.py <contrat.pdf|contrat.txt>")

    path = Path(sys.argv[1])
    if not path.exists():
        raise SystemExit(f"Fichier introuvable : {path}")

    print(f"Modèles (ordre d'essai) : {', '.join(MODELS)} | Prompt : {PROMPT_FILE.name}", flush=True)
    try:
        text = read_contract(path)
        if not text.strip():
            raise ExtractionError("Aucun texte extrait (PDF scanné ? il faudrait de l'OCR).")
        data = extract_clauses(text)
    except ExtractionError as err:
        raise SystemExit(str(err))

    print(f"Modèle utilisé : {data.get('modele_utilise')}\n")
    print_table(data)

    # On sauvegarde aussi le résultat brut : utile pour comparer tes versions de prompt.
    # Un fichier par exécution (prompt + modèle + heure) : rien n'est écrasé, et compare.py
    # peut comparer plusieurs essais d'un même prompt, ce qui est indispensable car l'IA varie.
    stamp = datetime.now().strftime("%H%M%S")
    out = path.with_suffix(f".{PROMPT_FILE.stem}.{data.get('modele_utilise', 'modele')}.{stamp}.result.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRésultat sauvegardé dans {out}")


if __name__ == "__main__":
    main()