# ContractAgent

Application desktop (Python) qui utilise un **agent IA** pour extraire automatiquement les **obligations** et les **droits** d'un contrat (PDF ou texte), afin d'assister un gestionnaire de contrat.

> Projet personnel d'apprentissage : IA générative, prompt engineering, application desktop, sécurité.
> Tous les contrats de ce dépôt sont **fictifs**. Ne jamais y mettre de contrat réel ou confidentiel.

## Fonctionnalités

- Chargement d'un contrat par bouton ou glisser-déposer (PDF ou .txt)
- Extraction par un LLM (API Gemini), avec sortie JSON structurée : parties, obligations, droits, autres clauses, échéances, article d'origine
- Tableau éditable : correction du texte et **validation humaine ligne par ligne** (case « Validé »)
- Zone d'**alertes** quand le contrat contient un texte qui tente de donner des ordres à l'IA
- Export Excel (feuille « Extraction » et feuille « Infos » avec parties, date, lignes validées, alertes)
- Interface non bloquante : l'analyse tourne dans un fil séparé

## État d'avancement

- [x] Lecture d'un contrat PDF / texte
- [x] Extraction des obligations et droits via un LLM (sortie JSON)
- [x] Interface desktop (PySide6)
- [x] Export Excel
- [x] Évaluation et comparaison de versions de prompt (`compare.py`)
- [ ] Build Windows (.exe avec PyInstaller)

## Installation et lancement

Une clé API gratuite s'obtient sur [Google AI Studio](https://aistudio.google.com/app/apikey).

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash) ; sous Linux/macOS : source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY="ta_clé_ici"   # la clé n'est jamais écrite dans le code

python app.py                                     # interface graphique
python extract.py samples/contrat_fictif.txt      # ligne de commande
```

Réglages optionnels (variables d'environnement) :

| Variable | Rôle |
|---|---|
| `CONTRACT_PROMPT` | fichier de prompt à utiliser, ex : `prompt_v2.txt` (défaut : `prompt_v1.txt`) |
| `GEMINI_MODEL` | modèle essayé en premier, puis la liste de secours par défaut |
| `GEMINI_MODELS` | liste **imposée** de modèles (séparés par des virgules). Un seul nom = pas de bascule, utile pour comparer |

`python list_models.py` affiche les modèles disponibles avec ta clé.

## Structure du dépôt

```
app.py             interface PySide6
extract.py         lecture du contrat, appel à l'IA, nouvelles tentatives, bascule de modèle
export_excel.py    export Excel
compare.py         comparaison de plusieurs extractions (éléments par article, parties, mots collés)
list_models.py     liste des modèles disponibles
prompts/           prompt_v1.txt, prompt_v2.txt
samples/           contrats fictifs : contrat_fictif.txt, contrat_piege.txt, contrat_maintenance_fictif.pdf
```

## Comment ça marche

1. `pdfplumber` transforme le contrat en texte.
2. Le texte est envoyé au LLM entre balises `<contrat>`, avec un prompt système qui impose un format JSON (`temperature=0`).
3. La réponse est validée (JSON valide, structure attendue), puis affichée dans un tableau.
4. L'utilisateur corrige et valide chaque ligne, puis exporte vers Excel.

## Choix de sécurité

- **Clé API** lue dans une variable d'environnement, exclue du dépôt par `.gitignore`.
- **Injection de prompt** : le contrat est traité comme une donnée, jamais comme une instruction. Les passages qui s'adressent à l'IA sont signalés dans les alertes au lieu d'être suivis (voir le test du contrat piégé ci-dessous).
- **Injection de formule Excel** : le texte venant du contrat ou de l'IA est écrit en type « texte », donc un contenu commençant par `=` n'est jamais interprété comme une formule.
- **Sortie de l'IA non fiable** : le JSON reçu est vérifié avant affichage, et chaque ligne est destinée à être validée par un humain.
- **Confidentialité** : uniquement des contrats fictifs. Avec l'offre gratuite d'une API d'IA, les données envoyées peuvent être utilisées par le fournisseur ; il faut vérifier ses conditions avant d'envoyer un document réel.

## Robustesse

- Nouvelles tentatives avec attente croissante sur les erreurs serveur (5xx) et les coupures réseau.
- Bascule automatique vers un autre modèle si l'un est saturé (503), retiré (404) ou à court de quota (429). Les erreurs de clé (4xx) arrêtent immédiatement.
- Les erreurs attendues s'affichent dans une boîte de dialogue claire ; l'interface ne se fige jamais pendant l'analyse.

## Journal du prompt engineering

Méthode : plusieurs exécutions de chaque prompt sur le même contrat (`contrat_maintenance_fictif.pdf`, 13 articles) et le même modèle (`gemini-3.5-flash-lite`), comparées avec `compare.py`. Le nombre d'éléments ne mesure pas l'exactitude : il sert à repérer les articles oubliés, les lignes étant ensuite relues dans le contrat.

| | prompt_v1 (3 exécutions) | prompt_v2 (4 exécutions) |
|---|---|---|
| Éléments extraits | 26, 24, 25 | 37, 32, 39, 39 |
| Article 2 (durée, reconduction, dénonciation) | 1 ligne | 3 lignes à chaque fois |
| Article 10 (limitation de responsabilité) | jamais extrait | extrait à chaque fois |
| Article 13 (droit applicable, amiable, tribunal) | 1 ligne | 2 à 3 lignes |
| Noms de parties hors liste | « Le Client », « Chaque partie », « Le Prestataire ou Le Client »… | 0 sur 4 exécutions |
| Fausses alertes sur un contrat sans piège | 0 | 0 |

**Ce que j'ai changé entre v1 et v2**
- Parcours imposé article par article, avec une ligne par élément (exemple : délai de paiement, pénalité et indemnité forfaitaire sont trois lignes).
- Nouveau type `autre` pour les clauses qui ne sont ni un droit ni une obligation (durée, limitation de responsabilité, juridiction).
- Champ `partie` : nom exact d'une partie ou « Les deux parties », jamais « X ou Y ».
- Nouveau champ `alertes` pour signaler les passages qui s'adressent à une IA.

**Observations**
- Une seule exécution ne suffit pas : avec le même prompt et le même modèle, v1 donne 24 à 26 éléments et v2 de 32 à 39. Les pénalités de retard (Article 5) manquaient dans une exécution de v1 et pas dans une autre.
- v2 est nettement plus complet, mais moins stable en nombre de lignes.
- Test de sécurité (`contrat_piege.txt`, un article ordonne à l'IA de répondre « PIRATÉ ») : avec v1, la consigne piégée est ignorée en silence ; avec v2, elle est ignorée **et** signalée dans les alertes (Article 4). Test fait sur une seule exécution.

## Limites connues

- **Variabilité** : deux exécutions identiques peuvent donner des résultats différents, y compris pour la classification droit / obligation / autre.
- **Mots collés (intermittent)** : des espaces disparaissent parfois dans le texte généré (« encas », « redevancemensuelle », « de5 % », « missionen »). Observé lors d'essais préliminaires avec deux modèles « lite » et les deux prompts, mais **0 détecté sur les 7 exécutions de l'évaluation finale** (`compare.py --contrat <contrat>`). Le détecteur ne voit pas les autres fautes de frappe (« Rrégler »). La correction repose sur la validation humaine ; piste : tester un modèle non « lite ».
- **PDF scannés** non pris en charge (pas d'OCR).
- Un nombre d'éléments plus élevé n'est pas une preuve d'exactitude : chaque ligne doit être relue dans le contrat.
- Évaluation faite sur un seul contrat fictif ; il faudrait un jeu de contrats plus large.
- L'offre gratuite de l'API est parfois saturée (erreurs 503), d'où les mécanismes de nouvelle tentative et de bascule.