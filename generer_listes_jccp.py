#!/usr/bin/env python3
"""Générer les listes de cartes (wikicode) des extensions du JCCP."""

import argparse
from types import SimpleNamespace

import generer_articles_jccp as jccp

CLASSE_TABLEAU = "tableaustandard sortable centre entetefixe"
CLASSE_TABLEAU_PROMO = "tableaustandard sortable centre"
COLONNES = (
    "Numéro",
    "Nom de la [[Carte Pokémon|carte]]",
    "[[Rareté]]",
    "Type",
)
COLONNES_PROMO = ("Numéro", "Nom de la carte", "Type", "Obtention")

# Sous-catégorie d'une carte Dresseur => cellule de la colonne Type
LIENS_SOUS_CATEGORIES = {
    "Objet": "[[Carte Objet|Objet]]",
    "Outil Pokémon": "[[Carte Outil Pokémon|Outil Pokémon]]",
    "Supporter": "[[Carte Supporter|Supporter]]",
    "Stade": "[[Carte Stade|Stade]]",
}

CELLULE_OUI = '| class="résistance" | ✓'
CELLULE_NON = '| class="faiblesse" | ✗'
INCONNU = "{{?}}"


# Données
def boosters_extension(master, code, loc):
    """Lister les boosters d'une extension, dans l'ordre du jeu."""
    # Les packs du tutoriel reprennent les noms des boosters : ignorés
    skus = {
        s["BasePackID"]: s["PackSkuID"]
        for s in master["PackSku"]
        if s["ExpansionID"] == code
        and not s["PackSkuID"].startswith("TUTORIAL")
    }
    packs = sorted(
        (p for p in master["PackMaster"] if p["PackID"] in skus),
        key=lambda p: (
            p.get("SortOrderPriority", 0),
            jccp.cle_naturelle(skus[p["PackID"]]),
        ),
    )
    promo = code.startswith("PROMO-")
    noms = (
        (loc.texte(pack["NameMSID"]), skus[pack["PackID"]]) for pack in packs
    )
    return list(
        dict.fromkeys(
            jccp.nom_booster(nom, sku, promo) for nom, sku in noms if nom
        )
    )


# Cellules
def cellule_nom(titre, decore, symbole):
    """Lier le nom à l'article, le symbole ex restant hors du lien."""
    if not (symbole and symbole in decore):
        return f"[[{titre}|{decore}]]"
    # Un discriminant suivant le symbole (de la Team Rocket) a son propre lien
    avant, _, apres = (partie.strip() for partie in decore.partition(symbole))
    return f"[[{titre}|{avant}]]{symbole}" + (
        f" [[{titre}|{apres}]]" if apres else ""
    )


def cellule_type(jeu, loc, genre, carte):
    """Retourner le type d'un Pokémon ou la sous-catégorie d'un Dresseur."""
    if genre == "pokemon":
        pokemon = jeu.pokemon[carte["PokemonID"]]
        type_carte = (loc.nom_type(pokemon["PokemonTypes"][0]) or "").lower()
        return "{{Type|" + type_carte + "|jcc}}" if type_carte else INCONNU
    dresseur = jeu.dresseurs[carte["TrainerID"]]
    sous_categories = jccp.SOUS_CATEGORIES_DRESSEUR.get(
        dresseur["TrainerType"], (INCONNU,)
    )
    return LIENS_SOUS_CATEGORIES.get(sous_categories[0], sous_categories[0])


# Tableau
def entete(ctx):
    """Retourner l'en-tête du tableau (boosters en colonnes si plusieurs)."""
    if ctx.promo:
        return [
            f'{{| class="{CLASSE_TABLEAU_PROMO}"',
            *(f"! {colonne}" for colonne in COLONNES_PROMO),
        ]
    if len(ctx.boosters) < 2:
        return [
            f'{{| class="{CLASSE_TABLEAU}"',
            *(f"! {colonne}" for colonne in COLONNES),
        ]
    obtention = "[[Booster (JCC)|Booster]] d'obtention"
    return [
        f'{{| class="{CLASSE_TABLEAU}"',
        *(f'! rowspan="2" | {colonne}' for colonne in COLONNES),
        f'! colspan="{len(ctx.boosters)}" | {obtention}',
        "|-",
        *(
            f"! [[Fichier:Logo Booster {ctx.nom_extension} {nom} JCCP.png"
            f"|Booster {nom}|x25px]]"
            for nom in ctx.boosters
        ),
    ]


def lignes_carte(ctx, entree):
    """Retourner les lignes de wikicode d'une carte du tableau."""
    jeu, loc = ctx.jeu, ctx.loc
    genre, carte = jeu.cartes[entree["CardID"]]
    msid = jccp.msid_nom(jeu, genre, carte)
    symbole = jccp.symbole_ex(jeu, genre, carte)
    numero = entree["CollectionNumber"]
    titre = jccp.formater_titre(loc.nom(msid), ctx.nom_extension, numero)
    decore = loc.nom(msid, "decore", symbole)
    boosters = ctx.boosters_par_carte.get(carte["CardID"], [])
    lignes = [
        "|-",
        f"| {numero:03d}<small>/{ctx.maximum}</small>",
        f"| {cellule_nom(titre, decore, symbole)}",
    ]
    if ctx.promo:
        obtention = "<br />".join(f"Booster {nom}" for nom in boosters)
        return [
            *lignes,
            f"| {cellule_type(jeu, loc, genre, carte)}",
            f"| {obtention or INCONNU}",
        ]
    rarete = jccp.RARETES.get(carte["Rarity"])
    lignes += [
        f"| {{{{Rareté JCC|{rarete}}}}}" if rarete else f"| {INCONNU}",
        f"| {cellule_type(jeu, loc, genre, carte)}",
    ]
    if len(ctx.boosters) >= 2:
        lignes += [
            CELLULE_OUI if nom in boosters else CELLULE_NON
            for nom in ctx.boosters
        ]
    return lignes


def generer_liste(master, jeu, loc, code):
    """Retourner le wikicode de la liste d'une extension et son nombre."""
    expansion = jeu.expansions[code]
    ctx = SimpleNamespace(
        jeu=jeu,
        loc=loc,
        promo=code.startswith("PROMO-"),
        nom_extension=jccp.nom_extension(loc, expansion),
        maximum=str(expansion.get("CollectionNumber", "")).strip() or INCONNU,
        boosters=boosters_extension(master, code, loc),
        boosters_par_carte=jccp.indexer_boosters(master, code, loc),
    )
    entrees = [
        entree
        for entree in jeu.entrees.get(code, [])
        if entree["CardID"] in jeu.cartes
    ]
    lignes = ["== Liste des cartes ==", *entete(ctx)]
    for entree in entrees:
        lignes += lignes_carte(ctx, entree)
    return "\n".join([*lignes, "|}"]) + "\n", len(entrees)


# Ligne de commande
def analyser_arguments(argv):
    """Analyser les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Chaque liste est écrite dans <sortie>/<extension>.txt.",
    )
    parser.add_argument(
        "extensions",
        nargs="*",
        metavar="extension",
        help="code(s) d'extension (A1, B4a, PROMO-B…) ; défaut : toutes",
    )
    jccp.ajouter_options_donnees(parser, jccp.DOSSIERS_DONNEES[:2])
    return jccp.resoudre_dossiers(parser, parser.parse_args(argv))


def main(argv=None):
    """Écrire la liste des cartes de chaque extension demandée."""
    args = analyser_arguments(argv)
    master = jccp.charger_master(args.master)
    jeu = jccp.construire_jeu(master)
    locs = jccp.charger_localisations(args.locale, jeu)
    loc = locs[jccp.LANGUE_PRINCIPALE]
    demandes = args.extensions or list(jeu.expansions)
    codes = dict.fromkeys(jccp.trouver_extension(jeu, d) for d in demandes)
    args.sortie.mkdir(parents=True, exist_ok=True)
    for code in codes:
        texte, nombre = generer_liste(master, jeu, loc, code)
        chemin = args.sortie / f"{code}.txt"
        chemin.write_text(texte, encoding="utf-8", newline="\n")
        print(f"{nombre} carte(s) listée(s) dans {chemin}")
    jccp.signaler_inconnues(locs)


if __name__ == "__main__":
    main()
