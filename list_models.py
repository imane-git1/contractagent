"""Liste les modèles Gemini utilisables avec ta clé API.

Usage :
    python list_models.py

Puis, pour en utiliser un sans modifier le code :
    export GEMINI_MODEL="nom_du_modèle"
    python extract.py samples/contrat_fictif.txt
"""

import os

from google import genai


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Variable GEMINI_API_KEY absente. Fais : export GEMINI_API_KEY=\"ta_clé\"")

    client = genai.Client(api_key=api_key)
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None)
        # On ne garde que les modèles capables de générer du texte.
        if actions is None or "generateContent" in actions:
            print(model.name.removeprefix("models/"))


if __name__ == "__main__":
    main()