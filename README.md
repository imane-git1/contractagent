# ContractAgent

Agent IA qui extrait automatiquement les **obligations** et les **droits** d'un contrat (PDF ou texte) pour assister un gestionnaire de contrat.

> Projet personnel d'apprentissage : IA générative, prompt engineering, application desktop Python.
> Tous les contrats utilisés dans ce dépôt sont **fictifs**.

## État d'avancement

- [x] Lecture d'un contrat PDF / texte
- [x] Extraction des obligations et droits via un LLM (sortie JSON)
- [x] Affichage en tableau dans le terminal
- [ ] Interface desktop (PySide6)
- [ ] Export Excel
- [ ] Évaluation et comparaison de versions de prompt
- [ ] Build Windows (.exe)

## Installation

Clé API gratuite : [Google AI Studio](https://aistudio.google.com/app/apikey).

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="ta_clé_ici"   # la clé n'est jamais écrite dans le code
python extract.py samples/contrat_fictif.txt
```

## Comment ça marche

1. `pdfplumber` transforme le contrat en texte.
2. Le texte est envoyé à un LLM avec un prompt système (`prompts/prompt_v1.txt`) qui impose un format JSON.
3. Le JSON est affiché sous forme de tableau et sauvegardé.

## Choix de sécurité

- Clé API lue dans une variable d'environnement, exclue du dépôt via `.gitignore`.
- Le prompt traite le contrat comme une donnée et non comme une instruction (protection contre l'injection de prompt).
- Aucun contrat réel ni confidentiel dans le dépôt.

## Journal du prompt engineering

_À compléter : pour chaque version du prompt, ce que j'ai changé et ce que j'ai observé._

## Limites connues

_À compléter au fil des tests._
