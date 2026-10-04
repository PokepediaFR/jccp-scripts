# jccp-scripts
Scripts pour les articles wiki du *JCC Pokémon Pocket*.

## Prérequis
* Avoir installé [Python](https://www.python.org/)
* Avoir [ajouté Python à son PATH](https://realpython.com/add-python-to-path/)

## Usage
Ces scripts dépendent entièrement du dossier `data` qui contient les sous-dossiers :
* `Descriptions` : les descriptions Pokédex dans les jeux de la série principale, récupérées depuis les textes des jeux
* `Locale` : les fichiers textes déchiffrés du *JCC Pokémon Pocket*
* `MasterMemory` : les jeux de données du *JCC Pokémon Pocket*

### Générer des articles wiki du JCC Pokémon Pocket
1. [Télécharger](https://github.com/PokepediaFR/jccp-scripts/archive/refs/heads/main.zip) ou cloner le dépôt (le dézipper si nécessaire)
2. Ouvrir un terminal dans le dossier du dépôt
3. Exécuter `python generer_articles_jccp.py` pour générer automatiquement des articles pour toutes les extensions
    * `python generer_articles_jccp.py A1 A4B Promo-A` permet par exemple de générer ces articles uniquement pour les extensions listées
    * `python generer_articles_jccp.py -n 12 A2` permet par exemple de générer uniquement l'article de la carte 012 de l'extension A2

Les articles sont générés au format texte dans le dossier `out/<code de l'extension>/`.

### Générer des redirections de fichiers des cartes
Le script concerné, `generer_redirections_jccp.py` doit être exécuté à côté de `generer_articles_jccp.py`. Il est principalement utilisé pour les extensions qui rééditent à l'identique une quantité non-négligeable de cartes, par exemple A4b et B4b, qui recyclent ainsi des images de cartes déjà été téléversée sur le wiki :
* Exécuter `python generer_redirections_jccp.py` pour générer des redirections de fichiers des cartes pour toutes les extensions
* Exécuter `python generer_redirections_jccp.py A4b B4b` pour générer des redirections de fichiers des cartes uniquement pour les extensions listées

Les redirections sont générées au format texte dans le dossier `redirects/<code de l'extension>/`.
