#!/usr/bin/env python3
"""Générer les redirections de fichiers des cartes déjà parues."""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from generer_articles_jccp import (
    DOSSIER_DONNEES,
    LANGUE_PRINCIPALE,
    charger_localisations,
    charger_master,
    construire_jeu,
    msid_nom,
    nom_extension,
    trouver_dossier,
    trouver_extension,
)

DOSSIER_REDIRECTIONS = "redirects"
MODELE = """#REDIRECTION [[Fichier:{cible}]]

[[Catégorie:Scan de carte de {extension}]]
[[Catégorie:{sujet}]]
"""


def nom_scan(extension, numero):
    """Retourner le nom du fichier de scan d'une carte sur le wiki."""
    return f"Carte {extension} {numero:03d}.png"


def indexer_parutions(jeu):
    """Lister, pour chaque carte, ses parutions triées chronologiquement."""
    parutions = defaultdict(list)
    for code, entrees in jeu.entrees.items():
        ordre = jeu.expansions[code]["SortOrderPriorityFromB1"]
        for entree in entrees:
            parutions[entree["CardID"]].append(
                (ordre, code, entree["CollectionNumber"])
            )
    for liste in parutions.values():
        liste.sort()
    return parutions


def sujet_scan(jeu, loc, genre, carte):
    """Retourner la catégorie de scan d'une carte (Pokémon ou Dresseur)."""
    if genre == "dresseur":
        return "Scan de carte Dresseur"
    nom = loc.nom(msid_nom(jeu, genre, carte), "reel")
    return f"Scan de carte représentant {nom}"


def ecrire_redirections(jeu, loc, parutions, noms, code, sortie):
    """Écrire les redirections d'une extension et retourner leur nombre."""
    dossier = sortie / code
    ecrites = 0
    for entree in jeu.entrees.get(code, []):
        if entree["CardID"] not in jeu.cartes:
            continue
        _, origine, numero_origine = parutions[entree["CardID"]][0]
        if origine == code:
            continue
        redirection = MODELE.format(
            cible=nom_scan(noms[origine], numero_origine),
            extension=noms[code],
            sujet=sujet_scan(jeu, loc, *jeu.cartes[entree["CardID"]]),
        )
        fichier = nom_scan(noms[code], entree["CollectionNumber"])
        chemin = dossier / (re.sub(r'[<>:"/\\|?*]', "_", fichier) + ".txt")
        dossier.mkdir(parents=True, exist_ok=True)
        chemin.write_text(redirection, encoding="utf-8", newline="\n")
        ecrites += 1
    print(f"{code} : {ecrites} redirection(s) écrite(s)")
    return ecrites


def generer(args):
    """Générer les redirections des extensions demandées."""
    jeu = construire_jeu(charger_master(args.master))
    demandes = args.extensions or list(jeu.expansions)
    codes = {trouver_extension(jeu, nom): None for nom in demandes}
    loc = charger_localisations(args.locale, jeu)[LANGUE_PRINCIPALE]
    noms = {c: nom_extension(loc, e) for c, e in jeu.expansions.items()}
    parutions = indexer_parutions(jeu)
    for code in codes:
        ecrire_redirections(jeu, loc, parutions, noms, code, args.sortie)


def analyser_arguments(argv):
    """Analyser les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description=(
            "Générer les redirections de fichiers (Fichier:Carte <extension> "
            "<numéro>.png) des cartes déjà parues dans une extension "
            "antérieure."
        ),
        epilog=(
            "Les redirections sont écrites dans <sortie>/<extension>/"
            "Carte <nom de l'extension> <numéro>.png.txt."
        ),
    )
    parser.add_argument(
        "extensions",
        nargs="*",
        metavar="extension",
        help="code(s) d'extension (A4b, B1, PROMO-B…) ; défaut : toutes",
    )
    for option, aide in (("master", "MasterMemory"), ("locale", "Locale")):
        parser.add_argument(
            f"--{option}",
            type=Path,
            help=f"dossier {aide} (défaut : '{DOSSIER_DONNEES}/{aide}')",
        )
    parser.add_argument(
        "-o",
        "--sortie",
        type=Path,
        default=Path(__file__).resolve().parent / DOSSIER_REDIRECTIONS,
        help=f"dossier de sortie (défaut : '{DOSSIER_REDIRECTIONS}')",
    )
    args = parser.parse_args(argv)
    for nom, defaut in (("master", "MasterMemory"), ("locale", "Locale")):
        dossier = getattr(args, nom) or trouver_dossier(defaut)
        if dossier is None or not dossier.is_dir():
            parser.error(f"--{nom} : dossier introuvable")
        setattr(args, nom, dossier)
    return args


def main(argv=None):
    """Exécuter la génération."""
    generer(analyser_arguments(argv))


if __name__ == "__main__":
    sys.exit(main())
