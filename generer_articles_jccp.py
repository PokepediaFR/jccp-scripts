#!/usr/bin/env python3
"""Générer les articles Poképédia (modèle Article carte) des cartes du JCCP."""

import argparse
import json
import re
import sys
from collections import defaultdict
from operator import attrgetter
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

# Fichiers et langues
DOSSIER_DONNEES = "data"
DOSSIER_SORTIE = "out"
NOMS_MASTER = (
    "Expansion ExpansionCollectionNumber PokemonCard Pokemon TrainerCard "
    "Trainer Character PokemonAttack PokemonAttackName PokemonAbility "
    "PokemonAbilityName PackSku PackMaster PackTableMaster PackTableCardMaster"
)
FICHIERS_MASTER = NOMS_MASTER.split()

LANGUE_PRINCIPALE = "fr_FR"
LANGUES = (LANGUE_PRINCIPALE, "en_US", "ja_JP")
LANG_RE = re.compile(r"^[A-Za-z]{2,3}[_-][A-Za-z]{2,4}$")
DESCRIPTION_RE = re.compile(r"^(\d{2})_(.+)$")

MAX_CARTES_IDENTIQUES = 3
MAX_BOOSTERS = 3


# Balises et textes du jeu
TAG_RE = re.compile(r"\[(/?)(\w+):(\w+)([^\]]*)\]")
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
ESPACES_RE = re.compile(r"[ \t]+")
SAUTS_RE = re.compile(r" ?\n[ \n]*")
CARD_ID_RE = re.compile(r"^[A-Z]+_\d+_(\d+)_(\d+)$")

GESTIONNAIRES = {
    ("Num", "Int"): "_entier",
    ("Gr", "Count"): "_accord",
    ("Img", "Element"): "_element",
    ("Img", "ex"): "_ex",
    ("Text", "CardName"): "_nom_carte",
    ("Text", "SpecialCondition"): "_condition",
    ("Text", "EvolutionPokemon"): "_evolution",
    ("Text", "AttackName"): "_nom_attaque",
    ("Text", "AbilityName"): "_nom_talent",
    ("Text", "AdditionalName"): "_discriminant",
}
CONTROLES = {
    ("", "Italic"): "''",
    ("/", "Italic"): "''",
    ("", "LI"): "\n# ",
}

SYMBOLE_EX = "{{Symbole JCC|ex JCCP}}"
SYMBOLE_EX_MEGA = "{{Symbole JCC|ex Méga}}"
# Le suffixe ex d'un nom, avec son séparateur (espace, trait d'union ou rien)
EX_RE = re.compile(r"(?:[ -]ex|(?<![A-Za-z])ex|(?<=[A-Za-z])ex$)(?![A-Za-z])")

# Type de discriminant (attribut type de la balise AdditionalName)
DISCRIMINANT_DRESSEUR = "C"
DISCRIMINANT_REGION = "region"
# Discriminants faisant partie du nom réel, pas de paramètre de forme
DISCRIMINANTS_NOM_REEL = (
    "ADDITIONAL_NAME_Akatsuki",  # Necrozma Ailes de l'Aurore
    "ADDITIONAL_NAME_Tasogare",  # Necrozma Crinière du Couchant
    "ADDITIONAL_NAME_Hisui",  # Formes de Hisui (comme les autres régions)
)
# Mots initiaux exclus de la valeur d'une forme (d'autres peuvent s'ajouter)
MOTS_EXCLUS_FORME = ("Forme",)
# Particules retirées d'un discriminant (de la Team Rocket, d'Alola…)
PARTICULES_RE = re.compile(r"^(?:de la |de l'|du |des |de |d')")


# Types, raretés et catégories
NOMS_ENERGIE = (
    "Colorless Grass Fire Water Lightning Psychic Fighting Darkness Metal "
    "Dragon"
)
TYPES_ENERGIE = dict(enumerate(NOMS_ENERGIE.split(), 1))
CODES_ELEMENT = dict(zip("CGRWLPFDM", NOMS_ENERGIE.split()))
NOMS_TYPES_JCC = (
    "plante feu eau électrique psy combat obscurité métal dragon incolore"
)
TYPES_JCC = NOMS_TYPES_JCC.split()

SYMBOLES_DEGATS = {0: "", 1: "+", 2: "×", 3: "-"}
# Catégories supplémentaires des Pokémon (AdditionalCategories du jeu)
CATEGORIE_ULTRA_CHIMERE = 1
TEMPS_PARADOXE = {2: "passé", 3: "futur"}
SOUS_CATEGORIES_DRESSEUR = {
    1: ("Supporter",),
    2: ("Objet",),
    3: ("Outil Pokémon",),
    4: ("Objet", "Fossile"),
    5: ("Stade",),
}

# Rareté du jeu => valeur du modèle Rareté JCC/nom anglais de la rareté
RARETES = {
    100: "1 losange",
    200: "2 losanges",
    300: "3 losanges",
    400: "4 losanges",
    500: "1 étoile",
    600: "2 étoiles",
    700: "2 étoiles",
    800: "3 étoiles",
    830: "chromatique 1",
    860: "chromatique 2",
    900: "couronne",
}
RARETES_EN = {
    500: "Illustration Rare",
    600: "Special Illustration Rare",
    700: "Super Rare",
    800: "Immersive Rare",
    830: "Shiny Rare",
    860: "Super Shiny Rare",
    900: "Crown Rare",
}
RARETES_FULL_ART = (500, 600, 700, 800, 860, 900)
RARETES_CHROMATIQUES = (830, 860)

RARETE_CHROMATIQUE_2 = 860
RARETES_2_ETOILES = (600, 700)
# Suffixes d'illustration correspondant à l'illustration de base d'une carte
ILLUSTRATIONS_NORMALES = ("C", "U", "R", "RR")

NOMS_SIGNATURE = (
    "nom categorie sous_categories type pv stade precedent retraite "
    "faiblesse facultes"
)
CLES_SIGNATURE = NOMS_SIGNATURE.split()
# Clés d'une faculté et nom du champ correspondant (ordre de sortie)
CHAMPS_FACULTE = (
    ("types", "type"),
    ("nom", "nom"),
    ("degats", "dégâts"),
    ("description", "description"),
)


# Liens wiki
def liens_avec_type(source, cible, lien, suffixe):
    """Construire les liens « source {{type}} suffixe » pour chaque type."""
    resultat = {}
    for type_jcc in TYPES_JCC:
        icone = "{{type|" + type_jcc + "|jcci}}"
        motif = source + r" *\{\{type\|" + type_jcc + r"\|jcci\}\} *"
        resultat[motif + suffixe] = f"{cible} {icone} [[{lien}|{suffixe}]]"
    return resultat


LIENS_WIKI = [
    {r"attaque": "[[Attaque (JCC)|attaque]]"},
    {
        r"Banc": "[[Banc (JCC)|Banc]]",
        r"Pokémon de Banc": "[[Pokémon de Banc]]",
    },
    {r"Brûlé": "[[Brûlure (JCC)|Brûlé]]"},
    {
        r"carte Dresseur": "[[Carte Dresseur (JCC)|carte Dresseur]]",
        r"cartes Dresseur": "[[Carte Dresseur (JCC)|cartes Dresseur]]",
    },
    {
        r"carte Énergie": "[[carte Énergie]]",
        r"cartes Énergie": "[[Carte Énergie|cartes Énergie]]",
        r"Énergie": "[[Énergie]]",
    },
    {
        **liens_avec_type(
            r"\[\[Énergie\]\]",
            "[[Énergie de base|Énergie]]",
            "Énergie de base",
            "de base",
        ),
        **liens_avec_type(
            r"\[\[carte Énergie\]\]",
            "[[Carte Énergie de base|carte Énergie]]",
            "Carte Énergie de base",
            "de base",
        ),
        **liens_avec_type(
            r"\[\[Carte Énergie\|cartes Énergie\]\]",
            "[[Carte Énergie de base|cartes Énergie]]",
            "Carte Énergie de base",
            "de base",
        ),
    },
    {
        r"carte Objet": "[[carte Objet]]",
        r"cartes Objet": "[[Carte Objet|cartes Objet]]",
    },
    {
        r"carte Outil Pokémon": "[[carte Outil Pokémon]]",
        r"cartes Outil Pokémon": (
            "[[Carte Outil Pokémon|cartes Outil Pokémon]]"
        ),
        r"Outil Pokémon": "[[Outil Pokémon]]",
        r"Outils Pokémon": "[[Outil Pokémon|Outils Pokémon]]",
    },
    {
        r"carte Stade": "[[carte Stade]]",
        r"cartes Stade": "[[Carte Stade|cartes Stade]]",
        r"Stade ": "[[Carte Stade|Stade]] ",
    },
    {
        r"carte Supporter": "[[carte Supporter]]",
        r"cartes Supporter": "[[Carte Supporter|cartes Supporter]]",
    },
    {r"Coût de Retraite": "[[Coût de Retraite]]"},
    {r"Confus": "[[Confusion (JCC)|Confus]]"},
    {r"Contrôle Pokémon": "[[Contrôle Pokémon]]"},
    {r"deck": "[[deck]]"},
    {
        r"défausse": "[[défausse]]",
        r"Défausse": "[[Défausse]]",
        r"pile de défausse": "[[pile de défausse]]",
    },
    {r"Empoisonné": "[[Empoisonnement (JCC)|Empoisonné]]"},
    {r"Endormi": "[[Sommeil (JCC)|Endormi]]"},
    {
        r"État Spécial": "[[État Spécial (JCC)|État Spécial]]",
        r"États Spéciaux": "[[État Spécial (JCC)|États Spéciaux]]",
    },
    {
        r"évoluer": "[[Évolution (JCC)|évoluer]]",
        r"Évolution": "[[Évolution (JCC)|Évolution]]",
        r"carte Évolution": "[[Évolution (JCC)|carte Évolution]]",
    },
    {r"Faiblesse": "[[Faiblesse (JCC)|Faiblesse]]"},
    {r"guérit": "[[Guérison (JCC)|guérit]]"},
    {r"K\.O\.": "[[K.O. (JCC)|K.O.]]"},
    {r"main": "[[main]]"},
    {r"\[\[main\]\]tenant": "maintenant"},
    {r"Paralysé": "[[Paralysie (JCC)|Paralysé]]"},
    {r"pièce": "[[Pièce (JCC)|pièce]]"},
    {
        r"Pokémon Actif": "[[Pokémon Actif]]",
        **liens_avec_type(
            r"Pokémon", "[[Pokémon Actif|Pokémon]]", "Pokémon Actif", "Actif"
        ),
    },
    {r"Pokémon Attaquant": "[[Pokémon Attaquant]]"},
    {
        r"Pokémon de base": "[[Pokémon de base]]",
        **liens_avec_type(
            r"Pokémon",
            "[[Pokémon de base|Pokémon]]",
            "Pokémon de base",
            "de base",
        ),
    },
    {r"Pokémon Défenseur": "[[Pokémon Défenseur]]"},
    {r"Pokémon Évolutif": "[[Pokémon Évolutif]]"},
    {r"Pokémon-ex": "[[Pokémon-ex]]"},
    {
        r"(\[\[Pokémon-ex\]\]|Pokémon-ex) Méga-"
        r"(\[\[Évolution \(JCC\)\|Évolution\]\]|Évolution)": (
            "[[Pokémon-ex Méga-Évolution]]"
        ),
    },
    {r"Poste Actif": "[[Poste Actif]]"},
    {r"Résistance": "[[Résistance (JCC)|Résistance]]"},
    {r"retraite": "[[retraite]]"},
    {
        r"soigner": "[[Soin (JCC)|soigner]]",
        r"soignez": "[[Soin (JCC)|soignez]]",
        r"Soignez": "[[Soin (JCC)|Soignez]]",
    },
    {r"talent": " [[Talent (JCC)|talent]]"},
    {r" type": " [[Type (JCC)|type]]"},
    {r"Ultra-Chimère": " [[Ultra-Chimère (JCC)|Ultra-Chimère]]"},
]

# Groupes de liens à appliquer et motifs correctifs
LIENS = [
    [(re.compile(m), r, "\\[" in m or "\\{" in m) for m, r in groupe.items()]
    for groupe in LIENS_WIKI
    if any("[[" in remplacement for remplacement in groupe.values())
]
MOTIFS_CORRECTIFS = [
    re.compile(motif)
    for groupe in LIENS_WIKI
    if not any("[[" in remplacement for remplacement in groupe.values())
    for motif in groupe
]
# Les liens et modèles déjà présents ne reçoivent pas de nouveau lien
PROTEGE_RE = re.compile(r"\[\[.*?\]\]|\{\{.*?\}\}")


# Types de données
class Carte(NamedTuple):
    """Entrée de l'index d'une carte dans une extension."""

    code: str
    numero: int
    card_id: str
    rarete: int
    illustration: tuple
    illustrateurs: tuple
    ordre: int
    msid: str


# Clé de tri chronologique d'une carte (extension puis numéro)
ORDRE_CARTE = attrgetter("ordre", "numero")


class Relations(NamedTuple):
    """Cartes identiques dans l'extension, réédition, illustration, couleur."""

    identiques: list
    reedition: Carte | None
    illustration: Carte | str | None
    couleur: bool


# Utilitaires
def lire_json(chemin):
    """Lire un fichier JSON en ignorant un éventuel BOM."""
    return json.loads(chemin.read_text(encoding="utf-8-sig"))


def cle_naturelle(composant):
    """Retourner une clé de tri numérique puis alphabétique."""
    return [
        (0, int(jeton), "") if jeton.isdigit() else (1, 0, jeton.lower())
        for jeton in re.split(r"(\d+)", composant)
        if jeton
    ]


def cle_rang(base, rang):
    """Retourner le nom d'un champ répété (base, base2, base3…)."""
    return base if rang == 1 else f"{base}{rang}"


def nombre(valeur):
    """Convertir une valeur en entier, ou None si impossible."""
    texte = str(valeur)
    return int(texte) if texte.lstrip("-").isdigit() else None


def nettoyer(texte):
    """Normaliser les espaces, apostrophes et signes d'un texte."""
    texte = ESPACES_RE.sub(" ", texte.replace("’", "'").replace("−", "–"))
    return SAUTS_RE.sub("\n", texte).strip()


def normaliser(texte):
    """Normaliser un texte pour comparer deux descriptions."""
    return " ".join(texte.replace("’", "'").split())


def ligne_unique(texte):
    """Fusionner un texte sur plusieurs lignes en une seule ligne."""
    return texte.replace("-\n", "-").replace("\n", " ") if texte else None


# Chargement des données
def trouver_dossier(nom):
    """Chercher un dossier dans data (dossier courant, puis du script)."""
    for base in (Path.cwd(), Path(__file__).resolve().parent):
        dossier = base / DOSSIER_DONNEES / nom
        if dossier.is_dir():
            return dossier
    return None


def trouver_extension(jeu, demande):
    """Retourner le code exact d'extension demandé (insensible à la casse)."""
    correspondances = {code.lower(): code for code in jeu.expansions}
    code = correspondances.get(demande.lower())
    if code is None:
        sys.exit(
            f"Extension inconnue : {demande}\nValeurs possibles : "
            + ", ".join(jeu.expansions)
        )
    return code


def charger_master(dossier):
    """Charger les fichiers JSON nécessaires de MasterMemory."""
    candidats = sorted(
        (c for c in dossier.rglob("*.json") if "__MACOSX" not in c.parts),
        key=lambda chemin: len(chemin.parts),
    )
    fichiers = {c.stem: c for c in reversed(candidats)}
    manquants = [nom for nom in FICHIERS_MASTER if nom not in fichiers]
    if manquants:
        sys.exit(
            "Fichiers manquants dans MasterMemory : " + ", ".join(manquants)
        )
    return {nom: lire_json(fichiers[nom]) for nom in FICHIERS_MASTER}


def construire_jeu(master):
    """Indexer les données MasterMemory."""
    entrees = defaultdict(list)
    for entree in master["ExpansionCollectionNumber"]:
        entrees[entree["ExpansionID"]].append(entree)
    for liste in entrees.values():
        liste.sort(key=lambda entree: entree["CollectionNumber"])
    cartes = {c["CardID"]: ("pokemon", c) for c in master["PokemonCard"]}
    cartes.update(
        {c["CardID"]: ("dresseur", c) for c in master["TrainerCard"]}
    )
    return SimpleNamespace(
        expansions={e["ExpansionID"]: e for e in master["Expansion"]},
        entrees=dict(entrees),
        cartes=cartes,
        pokemon={p["PokemonID"]: p for p in master["Pokemon"]},
        dresseurs={t["TrainerID"]: t for t in master["Trainer"]},
        personnages={
            c["CharacterID"]: c["DisplayNameMSID"] for c in master["Character"]
        },
        attaques={a["PokemonAttackID"]: a for a in master["PokemonAttack"]},
        noms_attaques={
            a["PokemonAttackNameID"]: a["NameMSID"]
            for a in master["PokemonAttackName"]
        },
        talents={a["PokemonAbilityID"]: a for a in master["PokemonAbility"]},
        noms_talents={
            a["PokemonAbilityNameID"]: a["NameMSID"]
            for a in master["PokemonAbilityName"]
        },
    )


def charger_localisations(dossier, jeu):
    """Charger les localisations nécessaires (français, anglais, japonais)."""
    trouves = defaultdict(list)
    for chemin in dossier.rglob("Master.json"):
        parties = chemin.relative_to(dossier).parts[:-1]
        rang = next(
            (i for i, p in enumerate(parties) if LANG_RE.match(p)), None
        )
        if rang is not None and "__MACOSX" not in parties:
            sous_dossiers = parties[rang:][1:]
            version = [cle_naturelle(p) for p in sous_dossiers]
            trouves[parties[rang]].append((version, chemin))
    if LANGUE_PRINCIPALE not in trouves:
        sys.exit(f"Langue {LANGUE_PRINCIPALE} introuvable dans Locale.")
    locs = {}
    for langue in LANGUES:
        if langue not in trouves:
            print(f"Avertissement : langue {langue} absente.", file=sys.stderr)
            continue
        textes = {}
        for _, chemin in sorted(trouves[langue], key=lambda item: item[0]):
            donnees = lire_json(chemin)
            if isinstance(donnees, dict):
                textes.update(donnees)
        locs[langue] = Localisation(textes, jeu, langue)
    return locs


def charger_descriptions(dossier):
    """Charger les descriptions des jeux, du plus récent au plus ancien."""
    if dossier is None:
        return []
    fichiers = sorted(
        (-int(trouve[1]), trouve[2], chemin)
        for chemin in dossier.glob("*.txt")
        if (trouve := DESCRIPTION_RE.match(chemin.stem))
    )
    lignes = {
        chemin: chemin.read_text(encoding="utf-8-sig").splitlines()
        for _, _, chemin in fichiers
    }
    return [
        (
            acronyme,
            {normaliser(ligne) for ligne in lignes[chemin] if ligne.strip()},
        )
        for _, acronyme, chemin in fichiers
    ]


# Textes localisés et liens
def est_dans_nom_reel(type_discriminant, cle):
    """Indiquer si un discriminant fait partie du nom réel de la carte."""
    return type_discriminant == DISCRIMINANT_REGION or (
        cle in DISCRIMINANTS_NOM_REEL
    )


def symboliser_ex(nom, symbole):
    """Remplacer le suffixe ex d'un nom par le symbole ex."""
    return EX_RE.sub(lambda _: symbole, nom, count=1)


def trouver_lien(texte, masque, groupe):
    """Retourner (début, fin, lien) du premier lien applicable d'un groupe."""
    candidats = sorted(
        (trouve.start(), trouve.start() - trouve.end(), trouve.end(), lien)
        for motif, lien, brut in groupe
        for trouve in motif.finditer(texte if brut else masque)
    )
    for debut, _, fin, lien in candidats:
        apres = lien + texte[fin:]
        if not any(correctif.match(apres) for correctif in MOTIFS_CORRECTIFS):
            return debut, fin, lien
    return None


class Lieur:
    """Ajouter les liens wiki d'un article, une seule fois chacun."""

    def __init__(self):
        """Initialiser la liste des groupes de liens déjà utilisés."""
        self.utilises = set()

    def lier(self, texte):
        """Lier la première occurrence des termes pas encore liés."""
        if not texte:
            return texte
        masque = None
        for rang, groupe in enumerate(LIENS):
            if rang in self.utilises:
                continue
            masque = masque or PROTEGE_RE.sub(
                lambda m: "\0" * len(m[0]), texte
            )
            trouve = trouver_lien(texte, masque, groupe)
            if trouve:
                debut, fin, lien = trouve
                texte = texte[:debut] + lien + texte[fin:]
                self.utilises.add(rang)
                masque = None
        return re.sub(r" {2,}", " ", texte).strip()


class Localisation:
    """Résoudre les textes localisés d'une langue (balises comprises)."""

    def __init__(self, textes, jeu, langue):
        """Mémoriser les textes, les index de noms du jeu et la langue."""
        self.textes = textes
        self.jeu = jeu
        self.langue = langue
        self.mode = "plain"
        self.inconnues = set()

    def brut(self, cle):
        """Retourner le texte brut d'une clé (première forme si liste)."""
        valeur = self.textes.get(cle) if cle else None
        if isinstance(valeur, list):
            valeur = valeur[0] if valeur else None
        return valeur if isinstance(valeur, str) else None

    def texte(self, cle, params=(), profondeur=0):
        """Retourner le texte rendu d'une clé, ou None si introuvable."""
        brut = self.brut(cle)
        if brut is None:
            return None
        return nettoyer(
            TAG_RE.sub(lambda m: self._balise(m, params, profondeur), brut)
        )

    def nom(self, cle, mode="plain", symbole=None):
        """Retourner un nom de carte (ex retiré en base/reel si symbole)."""
        ancien, self.mode = self.mode, mode
        try:
            texte = self.texte(cle)
        finally:
            self.mode = ancien
        if texte is None:
            return None
        if mode == "decore" and symbole:
            return symboliser_ex(texte, symbole)
        if mode in ("base", "reel") and symbole:
            return nettoyer(EX_RE.sub("", texte, count=1))
        return texte

    def discriminants(self, cle):
        """Lister les discriminants (type, clé, texte) du nom d'une carte."""
        resultat = []
        for _, espace, nom, attrs in TAG_RE.findall(self.brut(cle) or ""):
            if (espace, nom) == ("Text", "AdditionalName"):
                attributs = dict(ATTR_RE.findall(attrs))
                texte = self.texte(attributs.get("v"))
                resultat.append(
                    (attributs.get("type"), attributs.get("v"), texte or "")
                )
        return resultat

    def _balise(self, correspondance, params, profondeur):
        """Rendre une balise du jeu."""
        ferme, espace, nom, attrs = correspondance.groups()
        attributs = dict(ATTR_RE.findall(attrs))
        if espace == "C":
            return "-" if nom == "Nbh" else " "
        if espace == "Ctrl":
            return CONTROLES.get((ferme, nom), "")
        gestionnaire = GESTIONNAIRES.get((espace, nom))
        if gestionnaire:
            return getattr(self, gestionnaire)(attributs, params)
        if espace in ("Text", "Mst") and "v" in attributs and profondeur < 5:
            sous_texte = self.texte(attributs["v"], (), profondeur + 1) or ""
            espace_autour = attributs.get("space")
            if espace_autour == "pre":
                return " " + sous_texte
            return sous_texte + " " if espace_autour == "post" else sous_texte
        self.inconnues.add(f"{espace}:{nom}")
        return ""

    @staticmethod
    def _param(attributs, params, cle="id"):
        """Retourner le paramètre désigné par un attribut (0 par défaut)."""
        indice = int(attributs.get(cle) or 0)
        return params[indice] if indice < len(params) else None

    def _discriminant(self, attributs, *_):
        """Rendre un discriminant (région, forme, dresseur) d'un nom."""
        sous_texte = self.texte(attributs.get("v")) or ""
        dans_nom_reel = est_dans_nom_reel(
            attributs.get("type"), attributs.get("v")
        )
        if self.mode == "base" or (self.mode == "reel" and not dans_nom_reel):
            return ""
        if self.mode == "decore":
            sous_texte = f"<small>{sous_texte}</small>"
        espace = attributs.get("space")
        if espace == "pre":
            return " " + sous_texte
        if espace == "post" and self.langue != "ja_JP":
            return sous_texte + " "
        return sous_texte

    def _entier(self, attributs, params):
        """Afficher un nombre (seulement s'il est pluriel si demandé)."""
        valeur = self._param(attributs, params)
        if valeur is None:
            return ""
        if "plural_only" in attributs:
            separateur = attributs["plural_only"]
            return f"{valeur}{separateur}" if (nombre(valeur) or 0) > 1 else ""
        return str(valeur)

    def _accord(self, attributs, params):
        """Choisir la forme singulier/pluriel selon un nombre."""
        valeur = nombre(self._param(attributs, params, "ref"))
        if valeur == 1 and "one" in attributs:
            return attributs["one"]
        if valeur == 2 and "two" in attributs:
            return attributs["two"]
        if valeur == 1:
            return attributs.get("s", "")
        return attributs.get("p", "") if (valeur or 0) > 1 else ""

    def nom_type(self, numero):
        """Retourner le nom français d'un type d'énergie (numéro du jeu)."""
        anglais = TYPES_ENERGIE.get(numero)
        return (
            self.texte(f"ENERGY_TYPE_NAME_SHORT_{anglais}")
            if anglais
            else None
        )

    def _element(self, attributs, params):
        """Afficher l'icône d'un type d'énergie dans un texte."""
        code = attributs.get("name") or self._param(attributs, params)
        nom = self.texte(
            f"ENERGY_TYPE_NAME_SHORT_{CODES_ELEMENT.get(code, code)}"
        )
        if nom is None:
            self.inconnues.add(f"élément:{code}")
            return ""
        return "{{type|" + nom.lower() + "|jcci}}"

    @staticmethod
    def _ex(*_):
        """Afficher le suffixe ex d'un texte (Pokémon-ex)."""
        return "ex"

    def _nom_carte(self, attributs, params):
        """Afficher le nom d'un personnage de carte."""
        code = str(self._param(attributs, params))
        nom = self.nom(self.jeu.personnages.get(code))
        if nom is None:
            self.inconnues.add(f"carte:{code}")
            return code
        if code.endswith("_EX"):
            return symboliser_ex(
                nom, SYMBOLE_EX_MEGA if code.startswith("MEGA") else SYMBOLE_EX
            )
        return nom

    def _condition(self, attributs, params):
        """Afficher un état spécial (Endormi, Brûlé…)."""
        formes = self.textes.get(self._param(attributs, params))
        formes = sorted(
            formes if isinstance(formes, list) else [formes or ""], key=len
        )
        return formes[-1] if attributs.get("plural") else formes[0]

    def _evolution(self, attributs, params):
        """Afficher un stade d'évolution (Base, Niveau 1, Niveau 2…)."""
        stade = self.texte(f"EVOLUTION_STAGE_{self._param(attributs, params)}")
        return f"Pokémon de {stade}" if stade else "Pokémon"

    def _nom_attaque(self, attributs, params):
        """Afficher le nom d'une attaque."""
        code = self._param(attributs, params)
        return self.texte(self.jeu.noms_attaques.get(code)) or ""

    def _nom_talent(self, attributs, params):
        """Afficher le nom d'un talent."""
        code = self._param(attributs, params)
        return self.texte(self.jeu.noms_talents.get(code)) or ""


# Extensions et boosters
def nom_extension(loc, expansion):
    """Retourner le nom localisé d'une extension (ou son code)."""
    code = expansion["ExpansionID"]
    if code.startswith("PROMO-"):
        return "Promo-" + code.removeprefix("PROMO-")
    for cle in (expansion.get("LongNameMSID"), expansion.get("NameMSID")):
        nom = loc.texte(cle)
        if nom and nom != code:
            return nom
    return code


def nom_booster(nom, sku, promo):
    """Normaliser le nom d'un booster (promo : « promo série A, vol. 8 »)."""
    if promo:
        serie, _, volume = sku.removeprefix("PROMO-").partition("_")
        return f"promo série {serie}, vol. {volume}"
    return nom.split(" : ")[-1]


def indexer_boosters(master, code, loc):
    """Associer chaque carte aux boosters si l'extension en a plusieurs."""
    promo = code.startswith("PROMO-")
    skus = {
        s["BasePackID"]: s["PackSkuID"]
        for s in master["PackSku"]
        if s["ExpansionID"] == code
    }
    packs = {
        p["PackID"]: p for p in master["PackMaster"] if p["PackID"] in skus
    }
    if len(packs) < (1 if promo else 2):
        return {}
    tables = {
        t["PackTableID"] + "_": t["PackID"]
        for t in master["PackTableMaster"]
        if t["PackID"] in packs
    }
    par_carte = defaultdict(set)
    for entree in master["PackTableCardMaster"]:
        identifiant = entree["PackTableCardID"]
        if identifiant.startswith(tuple(tables)):
            pack = next(
                p for t, p in tables.items() if identifiant.startswith(t)
            )
            par_carte[entree["CardID"]].add(pack)
    resultat = {}
    for carte, ensemble in par_carte.items():
        ordre = sorted(ensemble, key=lambda pack: cle_naturelle(skus[pack]))
        noms = [loc.texte(packs[pack]["NameMSID"]) for pack in ordre]
        resultat[carte] = [
            nom_booster(nom, skus[pack], promo)
            for pack, nom in zip(ordre, noms)
            if nom
        ]
    return resultat


# Description des cartes
def msid_nom(jeu, genre, carte):
    """Retourner la clé de texte du nom d'une carte."""
    if genre == "pokemon":
        personnage = jeu.pokemon[carte["PokemonID"]]["CharacterID"]
    else:
        personnage = jeu.dresseurs[carte["TrainerID"]]["CharacterID"]
    return jeu.personnages.get(personnage)


def temps_paradoxe(personnage):
    """Retourner « passé » ou « futur » pour un Pokémon ou un Dresseur."""
    categories = personnage["AdditionalCategories"]
    return next(
        (t for c, t in TEMPS_PARADOXE.items() if c in categories), None
    )


def decrire_facultes_pokemon(jeu, loc, pokemon):
    """Décrire les talents puis les attaques d'un Pokémon."""
    facultes = []
    for rang, ident in enumerate(pokemon["PokemonAbilityIDs"], 1):
        talent = jeu.talents[ident]
        facultes.append(
            {
                "prefixe": cle_rang("talent", rang),
                "nom": loc.texte(
                    jeu.noms_talents.get(talent["PokemonAbilityNameID"])
                ),
                "description": loc.texte(
                    talent["DescriptionMSID"], talent["AbilityLogicParameters"]
                ),
            }
        )
    for rang, ident in enumerate(pokemon["PokemonAttackIDs"], 1):
        attaque = jeu.attaques[ident]
        degats = ""
        if attaque["Damage"] and not attaque["IsNoDamage"]:
            symbole = SYMBOLES_DEGATS[attaque["DamageSymbol"]]
            degats = str(attaque["Damage"]) + symbole
        facultes.append(
            {
                "prefixe": cle_rang("attaque", rang),
                "types": "".join(
                    "{{type|" + (loc.nom_type(cout) or "").lower() + "|jcc}}"
                    for cout in attaque["AttackCost"]
                )
                or "{{type|aucun|jcc}}",
                "nom": loc.texte(
                    jeu.noms_attaques.get(attaque["PokemonAttackNameID"])
                ),
                "description": loc.texte(
                    attaque["DescriptionMSID"],
                    attaque["AttackLogicParameters"],
                ),
                "degats": degats,
            }
        )
    return facultes


def decrire_pokemon(jeu, loc, carte):
    """Décrire les caractéristiques d'une carte Pokémon."""
    pokemon = jeu.pokemon[carte["PokemonID"]]
    precedent = jeu.personnages.get(pokemon["PreevolvedCharacterID"])
    faiblesse = pokemon["WeaknessType"]
    sous_categories = [
        nom
        for nom, present in (
            ("ex", pokemon["IsEX"]),
            ("Dresseur", pokemon["OwnerNameID"] == "TEAM_ROCKET"),
            ("Méga-Évolution", pokemon["IsMegaEvolution"]),
            (
                "Ultra-Chimère",
                CATEGORIE_ULTRA_CHIMERE in pokemon["AdditionalCategories"],
            ),
        )
        if present
    ]
    return {
        "categorie": "Pokémon",
        "sous_categories": sous_categories,
        "type": loc.nom_type(pokemon["PokemonTypes"][0]),
        "pv": pokemon["HP"],
        "stade": pokemon["EvolutionStage"] - 1,
        "precedent": loc.texte(precedent),
        "precedent_base": loc.nom(precedent, "base"),
        "temps": temps_paradoxe(pokemon),
        "retraite": pokemon["RetreatAmount"],
        "faiblesse": loc.nom_type(faiblesse) if faiblesse else None,
        "facultes": decrire_facultes_pokemon(jeu, loc, pokemon),
        "description": None
        if pokemon["IsEX"]
        else ligne_unique(loc.texte(carte["FlavorTextMSID"])),
    }


def decrire_dresseur(jeu, loc, carte):
    """Décrire les caractéristiques d'une carte Dresseur."""
    dresseur = jeu.dresseurs[carte["TrainerID"]]
    description = loc.texte(
        dresseur["DescriptionMSID"], dresseur["TrainerLogicParameters"]
    )
    return {
        "categorie": "Dresseur",
        "sous_categories": list(
            SOUS_CATEGORIES_DRESSEUR.get(dresseur["TrainerType"], ())
        ),
        "temps": temps_paradoxe(dresseur),
        "facultes": [{"prefixe": "faculté", "description": description}],
    }


def faits_carte(jeu, loc, genre, carte):
    """Décrire une carte en français, caractéristiques et textes."""
    decrire = decrire_pokemon if genre == "pokemon" else decrire_dresseur
    faits = decrire(jeu, loc, carte)
    faits["nom"] = loc.nom(msid_nom(jeu, genre, carte))
    return faits


def signature(faits):
    """Retourner une signature identifiant le texte et les caractéristiques."""
    contenu = {cle: faits.get(cle) for cle in CLES_SIGNATURE}
    return json.dumps(contenu, sort_keys=True, ensure_ascii=False)


def trouver_jeu(descriptions, texte):
    """Retourner l'acronyme du jeu le plus récent ayant cette description."""
    cible = normaliser(texte)
    return next((nom for nom, lignes in descriptions if cible in lignes), None)


def nettoyer_forme(texte):
    """Retirer les mots exclus et les particules au début d'un discriminant."""
    for mot in MOTS_EXCLUS_FORME:
        texte = texte.removeprefix(mot + " ")
    return PARTICULES_RE.sub("", texte)


def decrire_noms(donnees, genre, carte):
    """Décrire les noms d'une carte dans toutes les langues utiles."""
    jeu = donnees.jeu
    msid = msid_nom(jeu, genre, carte)
    symbole = None
    if genre == "pokemon" and jeu.pokemon[carte["PokemonID"]]["IsEX"]:
        mega = jeu.pokemon[carte["PokemonID"]]["IsMegaEvolution"]
        symbole = SYMBOLE_EX_MEGA if mega else SYMBOLE_EX
    loc_fr = donnees.locs[LANGUE_PRINCIPALE]
    reel = loc_fr.nom(msid, "reel", symbole)
    formes = {"forme": None, "dresseur": None}
    for type_discriminant, cle, texte in loc_fr.discriminants(msid):
        if type_discriminant == DISCRIMINANT_DRESSEUR:
            formes["dresseur"] = nettoyer_forme(texte)
        elif not est_dans_nom_reel(type_discriminant, cle):
            formes["forme"] = nettoyer_forme(texte)
    decores = {
        langue: loc.nom(msid, "decore", symbole)
        for langue, loc in donnees.locs.items()
    }
    nom_reel = reel if reel != decores[LANGUE_PRINCIPALE] else None
    return {"noms_decores": decores, "nom_reel": nom_reel, **formes}


# Index, rééditions et cartes identiques
def cle_illustration(carte):
    """Retourner une clé identifiant l'illustration d'une carte."""
    suffixe = carte["IllustrationID"].rsplit("_", 1)[-1]
    classe = "normale" if suffixe in ILLUSTRATIONS_NORMALES else "speciale"
    correspondance = CARD_ID_RE.match(carte["CardID"])
    if not correspondance:
        return (carte["CardID"], classe)
    numero, version = correspondance.groups()
    # Une carte reverse a l'illustration de sa jumelle (version 00)
    return (numero, "00" if carte["MirrorType"] else version, classe)


def creer_entree(jeu, code, entree):
    """Créer l'entrée d'index d'une carte de l'extension."""
    genre, carte = jeu.cartes[entree["CardID"]]
    return Carte(
        code=code,
        numero=entree["CollectionNumber"],
        card_id=carte["CardID"],
        rarete=carte["Rarity"],
        illustration=cle_illustration(carte),
        illustrateurs=tuple(carte["IllustratorNameMSIDs"]),
        ordre=jeu.expansions[code]["SortOrderPriorityFromB1"],
        msid=msid_nom(jeu, genre, carte),
    )


def indexer_signatures(jeu, loc, codes):
    """Indexer par signature les cartes de même nom que celles visées."""
    lignes = []
    noms = {}
    for code, liste in jeu.entrees.items():
        for entree in liste:
            if entree["CardID"] not in jeu.cartes:
                continue
            genre, carte = jeu.cartes[entree["CardID"]]
            msid = msid_nom(jeu, genre, carte)
            if msid not in noms:
                noms[msid] = loc.nom(msid)
            lignes.append((code, entree, genre, carte, noms[msid]))
    voulus = {nom for code, _, _, _, nom in lignes if code in codes}
    cache = {}
    index = defaultdict(list)
    for code, entree, genre, carte, nom in lignes:
        if nom not in voulus:
            continue
        cle = (
            genre,
            carte["PokemonID" if genre == "pokemon" else "TrainerID"],
        )
        if cle not in cache:
            cache[cle] = signature(faits_carte(jeu, loc, genre, carte))
        index[cache[cle]].append(creer_entree(jeu, code, entree))
    return index


def memes_illustrations(carte, autre):
    """Indiquer si deux cartes ont la même illustration."""
    return carte.card_id == autre.card_id or (
        carte.illustration == autre.illustration
        and carte.illustrateurs == autre.illustrateurs
    )


def chercher_relations(index, courante, cle):
    """Chercher les cartes identiques et la réédition d'une carte."""
    memes = index[cle]
    identiques = sorted(
        (
            carte
            for carte in memes
            if carte.code == courante.code and carte.numero != courante.numero
        ),
        key=lambda carte: carte.numero,
    )
    precedentes = [
        carte
        for carte in memes
        if carte.code != courante.code and carte.ordre < courante.ordre
    ]
    if not precedentes:
        return Relations(identiques, None, None, False)
    meme_art = [c for c in precedentes if memes_illustrations(c, courante)]
    if meme_art:
        reedition = source = min(meme_art, key=ORDRE_CARTE)
        illustration = None
    else:
        reedition = min(precedentes, key=ORDRE_CARTE)
        source = None
        if courante.rarete == RARETE_CHROMATIQUE_2:
            source = min(
                (
                    c
                    for c in precedentes
                    if c.rarete in RARETES_2_ETOILES
                    and c.illustrateurs == courante.illustrateurs
                ),
                key=ORDRE_CARTE,
                default=None,
            )
        illustration = "différente" if source is None else source
        if source is reedition:
            illustration = None
    couleur = (
        courante.rarete == RARETE_CHROMATIQUE_2
        and source is not None
        and source.rarete in RARETES_2_ETOILES
    )
    return Relations(identiques, reedition, illustration, couleur)


def titre_carte(donnees, carte):
    """Retourner le titre français de l'article d'une carte de l'index."""
    loc = donnees.locs[LANGUE_PRINCIPALE]
    extension = donnees.ctx.expansions_fr[carte.code]
    return f"{loc.nom(carte.msid)} ({extension} {carte.numero:03d})"


def decrire_carte(donnees, entree):
    """Décrire une carte de l'extension pour son article."""
    jeu = donnees.jeu
    genre, carte = jeu.cartes[entree["CardID"]]
    loc = donnees.locs[LANGUE_PRINCIPALE]
    faits = faits_carte(jeu, loc, genre, carte)
    faits.update(decrire_noms(donnees, genre, carte))
    courante = creer_entree(jeu, donnees.ctx.code, entree)
    illustrateurs = (loc.texte(m) for m in carte["IllustratorNameMSIDs"])
    faits.update(
        entree=courante,
        numero=courante.numero,
        rarete_code=courante.rarete,
        illustrateurs=[nom for nom in illustrateurs if nom],
        boosters=donnees.boosters.get(carte["CardID"], [])[:MAX_BOOSTERS],
        relations=chercher_relations(
            donnees.index, courante, signature(faits)
        ),
    )
    return faits


# Formatage des articles
def artwork_precedent(faits):
    """Retourner l'artwork de l'évolution précédente (Pokémon de Dresseur)."""
    base = faits.get("precedent_base")
    if faits.get("dresseur") and faits.get("stade") and base:
        return f"{base}.png"
    return None


def champs_infobox(faits, ctx):
    """Retourner les champs de l'infobox d'une carte."""
    noms = faits["noms_decores"]
    numero = faits["numero"]
    code = faits["rarete_code"]
    secrete = ctx.max_set.isdigit() and numero > int(ctx.max_set)
    sous_categories = [
        (cle_rang("sous-catégorie", rang), sous_categorie)
        for rang, sous_categorie in enumerate(faits["sous_categories"], 1)
    ]
    illustrateurs = [
        (cle_rang("illus", rang), illustrateur)
        for rang, illustrateur in enumerate(faits["illustrateurs"][:2], 1)
    ]
    return [
        ("nom", noms[LANGUE_PRINCIPALE]),
        ("nomréel", faits["nom_reel"]),
        ("forme", faits["forme"]),
        ("nomen", noms.get("en_US")),
        ("nomja", noms.get("ja_JP")),
        ("extension", ctx.expansions_fr[ctx.code]),
        ("jeu", "jccp"),
        ("numerocarte", f"{numero:03d}"),
        ("maxsetcarte", ctx.max_set),
        ("rareté", "aucune" if ctx.promo else RARETES.get(code)),
        ("secrète", "oui" if secrete else None),
        ("type", faits.get("type")),
        ("pv", faits.get("pv")),
        ("stade", faits.get("stade")),
        ("niveau-précédent", faits.get("precedent")),
        ("niveau-précédent-artwork", artwork_precedent(faits)),
        ("retraite", faits.get("retraite")),
        ("faiblesse", faits.get("faiblesse")),
        ("full-art", "oui" if code in RARETES_FULL_ART else None),
        ("catégorie", faits["categorie"]),
        *sous_categories,
        ("temps", faits.get("temps")),
        ("dresseur", faits["dresseur"]),
        *illustrateurs,
    ]


def champs_facultes(faits):
    """Retourner les champs des talents, attaques et effets d'une carte."""
    champs = []
    lieur = Lieur()
    for faculte in faits["facultes"]:
        prefixe = faculte["prefixe"]
        for cle, nom_champ in CHAMPS_FACULTE:
            valeur = faculte.get(cle)
            if cle == "description":
                valeur = lieur.lier(valeur)
            champs.append((f"{prefixe}-{nom_champ}", valeur))
    return champs


def champs_description(faits, descriptions):
    """Retourner les champs de description (avec le jeu et la forme)."""
    description = faits.get("description")
    if not description:
        return []
    return [
        ("description", description),
        ("description-jeu", trouver_jeu(descriptions, description)),
        ("description-forme", faits["forme"]),
    ]


def champs_anecdotes(faits, donnees):
    """Retourner les champs d'anecdotes (boosters, chromatique, réédition)."""
    champs = [
        (cle_rang("booster", rang), booster)
        for rang, booster in enumerate(faits["boosters"], 1)
    ]
    if faits["rarete_code"] in RARETES_CHROMATIQUES:
        champs.append(("chromatique", "oui"))
    relations = faits["relations"]
    if relations.reedition:
        illustration = relations.illustration
        if isinstance(illustration, Carte):
            illustration = titre_carte(donnees, illustration)
        champs += [
            ("réédition", titre_carte(donnees, relations.reedition)),
            ("réédition-illustration", illustration),
            ("réédition-couleur", "différente" if relations.couleur else None),
        ]
    return champs


def champs_identiques(faits, donnees):
    """Retourner les champs des cartes identiques dans l'extension."""
    identiques = faits["relations"].identiques[:MAX_CARTES_IDENTIQUES]
    return [
        (cle_rang("carte-identique", rang), titre_carte(donnees, carte))
        for rang, carte in enumerate(identiques, 1)
    ]


def lignes_bloc(titre, champs):
    """Formater un bloc de champs du modèle (vide si aucun champ)."""
    lignes = [
        f"| {cle}={valeur}"
        for cle, valeur in champs
        if valeur not in (None, "")
    ]
    return "\n".join([f"<!-- {titre} -->", *lignes]) if lignes else ""


def liens_interwiki(faits, donnees):
    """Retourner le lien interwiki anglais d'une carte (liste vide sinon)."""
    ctx = donnees.ctx
    # relations = faits["relations"]
    courante = faits["entree"]
    loc_en = donnees.locs.get("en_US")
    # cible = relations.reedition or courante
    cible = courante
    # if not relations.reedition and relations.identiques:
    #     premiere = relations.identiques[0]
    #     cible = premiere if premiere.numero < courante.numero else courante
    nom = loc_en.nom(cible.msid) if loc_en else None
    extension = ctx.expansions_en.get(cible.code)
    if not nom or not extension:
        return []
    titre = f"{nom} ({extension} {cible.numero})"
    ancre = "Promo" if ctx.promo else RARETES_EN.get(courante.rarete)
    if cible is not courante and ancre:
        titre += f"#{ancre}-0"
    return [f"[[en:{titre}]]"]


def formater_article(faits, donnees):
    """Générer le wikicode complet de l'article d'une carte."""
    blocs = (
        lignes_bloc("Infobox", champs_infobox(faits, donnees.ctx)),
        lignes_bloc("Facultés", champs_facultes(faits)),
        lignes_bloc(
            "Description", champs_description(faits, donnees.descriptions)
        ),
        lignes_bloc("Anecdotes", champs_anecdotes(faits, donnees)),
        lignes_bloc("Cartes identiques", champs_identiques(faits, donnees)),
    )
    modele = "{{Article carte\n" + "\n\n".join(b for b in blocs if b) + "\n}}"
    return "\n\n".join([modele, *liens_interwiki(faits, donnees)]) + "\n"


# Génération et ligne de commande
def creer_contexte(jeu, code, noms_fr, noms_en):
    """Créer le contexte (numéro max, promo, noms) d'une extension."""
    maximum = str(jeu.expansions[code].get("CollectionNumber", "")).strip()
    if maximum.isdigit():
        maximum = f"{int(maximum):03d}"
    return SimpleNamespace(
        code=code,
        max_set=maximum,
        promo=code.startswith("PROMO-"),
        expansions_fr=noms_fr,
        expansions_en=noms_en,
    )


def ecrire_extension(donnees, numeros, sortie):
    """Écrire tous les articles d'une extension et retourner leur nombre."""
    code = donnees.ctx.code
    dossier = sortie / code
    dossier.mkdir(parents=True, exist_ok=True)
    ecrits = 0
    for entree in donnees.jeu.entrees.get(code, []):
        if entree["CardID"] not in donnees.jeu.cartes:
            continue
        if numeros and entree["CollectionNumber"] not in numeros:
            continue
        faits = decrire_carte(donnees, entree)
        titre = titre_carte(donnees, faits["entree"])
        chemin = dossier / (re.sub(r'[<>:"/\\|?*]', "_", titre) + ".txt")
        chemin.write_text(
            formater_article(faits, donnees), encoding="utf-8", newline="\n"
        )
        ecrits += 1
    print(f"{ecrits} article(s) écrit(s) dans {dossier}")
    return ecrits


def generer(args):
    """Générer tous les articles des extensions demandées."""
    master = charger_master(args.master)
    jeu = construire_jeu(master)
    demandes = args.extensions or list(jeu.expansions)
    codes = {trouver_extension(jeu, nom): None for nom in demandes}
    locs = charger_localisations(args.locale, jeu)
    loc_fr, loc_en = locs[LANGUE_PRINCIPALE], locs.get("en_US")
    if args.descriptions is None:
        print(
            "Avertissement : dossier Descriptions introuvable, "
            "description-jeu non renseigné.",
            file=sys.stderr,
        )
    noms_fr = {c: nom_extension(loc_fr, e) for c, e in jeu.expansions.items()}
    noms_en = {
        c: nom_extension(loc_en, e)
        for c, e in jeu.expansions.items()
        if loc_en
    }
    index = indexer_signatures(jeu, loc_fr, codes)
    descriptions = charger_descriptions(args.descriptions)
    for code in codes:
        donnees = SimpleNamespace(
            jeu=jeu,
            locs=locs,
            ctx=creer_contexte(jeu, code, noms_fr, noms_en),
            index=index,
            boosters=indexer_boosters(master, code, loc_fr),
            descriptions=descriptions,
        )
        ecrire_extension(donnees, args.numero, args.sortie)
    inconnues = set().union(*(loc.inconnues for loc in locs.values()))
    if inconnues:
        print(
            "Balises non gérées : " + ", ".join(sorted(inconnues)),
            file=sys.stderr,
        )


def analyser_arguments(argv):
    """Analyser les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description=(
            "Générer les articles Poképédia (modèle Article carte) d'une ou "
            "plusieurs cartes du JCCP à partir de MasterMemory et Locale."
        ),
        epilog=(
            "Les articles sont écrits dans <sortie>/<extension>/"
            "<titre de l'article>.txt."
        ),
    )
    parser.add_argument(
        "extensions",
        nargs="*",
        metavar="extension",
        help="code(s) d'extension (A4b, B1, PROMO-B…) ; défaut : toutes",
    )
    for option, aide in (
        ("master", "MasterMemory"),
        ("locale", "Locale"),
        ("descriptions", "Descriptions"),
    ):
        parser.add_argument(
            f"--{option}",
            type=Path,
            help=f"dossier {aide} (défaut : '{DOSSIER_DONNEES}/{aide}')",
        )
    parser.add_argument(
        "-o",
        "--sortie",
        type=Path,
        default=Path(__file__).resolve().parent / DOSSIER_SORTIE,
        help=f"dossier de sortie (défaut : '{DOSSIER_SORTIE}')",
    )
    parser.add_argument(
        "-n",
        "--numero",
        type=int,
        action="append",
        help="ne générer que cette carte (option répétable : -n 12 -n 13)",
    )
    args = parser.parse_args(argv)
    for nom, defaut in (("master", "MasterMemory"), ("locale", "Locale")):
        dossier = getattr(args, nom) or trouver_dossier(defaut)
        if dossier is None or not dossier.is_dir():
            parser.error(f"--{nom} : dossier introuvable")
        setattr(args, nom, dossier)
    args.descriptions = args.descriptions or trouver_dossier("Descriptions")
    return args


def main(argv=None):
    """Exécuter la génération."""
    generer(analyser_arguments(argv))


if __name__ == "__main__":
    main()
