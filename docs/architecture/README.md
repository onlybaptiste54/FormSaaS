# Architecture produit — la page

Ce dossier décrit ce que l'agent doit savoir construire, pas comment le code est écrit.

## Exemple de référence

[exemple-landing-page-agences.pdf](exemple-landing-page-agences.pdf) — une page de captation destinée aux agences. C'est le niveau de rendu attendu d'une **page** produite par Luna : pas une maquette à recopier, une cible de qualité et un inventaire de ce qu'une page doit pouvoir contenir.

## Ce que l'exemple apprend

Une page n'est pas un document libre : c'est une **suite verticale de sections**, chacune d'un type connu. L'exemple en enchaîne neuf, dans cet ordre :

| # | Section | Contenu |
| --- | --- | --- |
| 1 | Barre de navigation | Logo, liens d'ancrage, bouton d'action |
| 2 | Accroche | Sur-titre, titre, paragraphe, deux boutons, encart illustré à droite |
| 3 | Constat | Titre, trois colonnes numérotées, sur fond sombre |
| 4 | Étapes | Titre, trois cartes numérotées |
| 5 | Texte et visuel | Titre, paragraphe, mention légale, visuel à droite |
| 6 | Offre | Titre, paragraphe, carte de prix avec liste à cocher et bouton |
| 7 | Questions fréquentes | Paires question / réponse sur deux colonnes |
| 8 | Formulaire | Titre, paragraphe, le formulaire lui-même, consentement et mentions |
| 9 | Pied de page | Raison sociale, liens légaux |

Trois conséquences pour le modèle de données :

1. **Le nombre de sections est variable.** Un squelette figé ne suffit pas : il faut une liste ordonnée, comme `fields` l'est déjà pour un formulaire.
2. **Le formulaire est une section parmi d'autres** (section 8), pas un objet d'un autre genre posé à côté.
3. **Chaque section a un type fermé et des zones nommées.** C'est ce qui permet à Luna de viser une zone précise quand l'utilisateur encadre et dit « modifie ça » — le même mécanisme que sur les champs aujourd'hui.

## Ce qui reste à trancher

La liste des types de section retenus pour la première version, et l'ordre dans lequel on les dessine. L'exemple en montre neuf ; tous ne sont pas nécessaires pour livrer.
