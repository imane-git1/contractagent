"""Compare plusieurs résultats d'extraction (fichiers .result.json), sans appeler l'IA.

Usage :
    python extract.py samples/contrat_maintenance_fictif.pdf
    CONTRACT_PROMPT=prompt_v2.txt python extract.py samples/contrat_maintenance_fictif.pdf
    python compare.py samples/contrat_maintenance_fictif.*.result.json
    python compare.py --contrat samples/contrat_maintenance_fictif.pdf samples/contrat_maintenance_fictif.*.result.json

Avec --contrat, l'outil repère aussi les mots collés (« encas », « redevancemensuelle ») : un mot absent
du contrat qui est la concaténation de deux mots du contrat, ou des lettres collées à un chiffre (« de5 »).

Affiche, pour chaque version (A, B, ...), le nombre d'éléments par article, le total par type,
les noms de parties douteux et les alertes. C'est la base de ton journal de prompt engineering.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

BOTH_PARTIES = "les deux parties"


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clause_key(clause) -> tuple:
    """Clé de tri : « Article 10 » après « Article 9 »."""
    label = (clause or "").strip() or "(sans clause)"
    number = re.search(r"\d+", label)
    return (int(number.group()) if number else 10**6, label)


def words(text: str) -> list:
    return re.findall(r"\w+", text.lower())


def glued_words(text: str, vocab: set) -> list:
    """Mots probablement « collés » : espace manquant entre deux mots du contrat."""
    found = []
    for word in words(text):
        if word in vocab or word.isdigit():
            continue
        if re.fullmatch(r"[^\W\d_]+\d+", word):  # « de5 » : lettres collées à un chiffre
            found.append(word)
        elif word.isalpha() and len(word) >= 5 and any(
            word[:i] in vocab and word[i:] in vocab for i in range(2, len(word) - 1)
        ):
            found.append(word)
    return found


def main() -> None:
    args = sys.argv[1:]
    contract_path = None
    if "--contrat" in args:
        position = args.index("--contrat")
        if position + 1 >= len(args):
            raise SystemExit("Après --contrat, indique le fichier du contrat (PDF ou .txt).")
        contract_path = args[position + 1]
        del args[position : position + 2]
    files = args
    if not files:
        raise SystemExit("Usage : python compare.py [--contrat contrat.pdf] resultat1.result.json [resultat2.result.json ...]")

    vocab = None
    if contract_path:
        from extract import read_contract  # importé ici : seulement si on en a besoin

        vocab = set(words(read_contract(Path(contract_path))))

    letters = "ABCDEFGH"
    datas = [load(f) for f in files]
    for letter, path, data in zip(letters, files, datas):
        print(f"{letter} = {Path(path).name}  (modèle : {data.get('modele_utilise', '?')})")
    print()

    per_clause = [Counter((e.get("clause") or "").strip() or "(sans clause)" for e in d["elements"]) for d in datas]
    clauses = sorted({c for counter in per_clause for c in counter}, key=clause_key)

    header = f"{'CLAUSE':<18}" + "".join(f"{letter:>5}" for letter in letters[: len(datas)])
    print(header)
    print("-" * len(header))
    for clause in clauses:
        print(f"{clause:<18}" + "".join(f"{counter.get(clause, 0):>5}" for counter in per_clause))
    print("-" * len(header))
    print(f"{'TOTAL':<18}" + "".join(f"{len(d['elements']):>5}" for d in datas))

    types = sorted({str(e.get("type")) for d in datas for e in d["elements"]})
    for kind in types:
        counts = [sum(1 for e in d["elements"] if str(e.get("type")) == kind) for d in datas]
        print(f"{kind:<18}" + "".join(f"{n:>5}" for n in counts))

    print("\nNoms de parties qui ne sont ni un nom de la liste « parties » ni « Les deux parties » :")
    print("(règle ajoutée dans prompt_v2 : « Le Client » est donc normal avec prompt_v1)")
    for letter, data in zip(letters, datas):
        known = {str(p).strip().lower() for p in data.get("parties") or []} | {BOTH_PARTIES}
        bad = [str(e.get("partie") or "(vide)").strip() for e in data["elements"]]
        bad = [name for name in bad if name.lower() not in known]
        examples = " | ".join(sorted(set(bad))[:3])
        print(f"  {letter} : {len(bad)} sur {len(data['elements'])}" + (f"   ex : {examples}" if bad else ""))

    print("\nAlertes : " + ", ".join(f"{letter} = {len(d.get('alertes') or [])}" for letter, d in zip(letters, datas)))

    if vocab is None:
        print("\n(Ajoute --contrat samples/ton_contrat.pdf pour détecter les mots collés comme « encas ».)")
    else:
        print("\nMots collés probables (espace manquant) :")
        for letter, data in zip(letters, datas):
            hits = []
            for e in data["elements"]:
                hits += glued_words(f"{e.get('description') or ''} {e.get('echeance') or ''}", vocab)
            examples = " | ".join(sorted(set(hits))[:4])
            print(f"  {letter} : {len(hits)}" + (f"   ex : {examples}" if hits else ""))


if __name__ == "__main__":
    main()