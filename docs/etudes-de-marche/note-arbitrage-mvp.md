# Note d'arbitrage — le MVP face aux trois segments

**Périmètre MVP annoncé :** formulaire créé par l'IA, à la charte graphique de l'entreprise à partir du logo et de fichiers partagés, avec hébergement rapide.

---

## 1. Ce que ce MVP couvre, segment par segment

| Segment | Couvert par le MVP ? | Ce qui manque pour vendre |
|---|---|---|
| **1. Agences** | ⚠️ Partiellement | La gestion multi-comptes. Une agence ne veut pas un formulaire, elle en veut quarante, rangés par client |
| **2. TPE en direct** | ✅ Oui, sur la promesse visible | Rien techniquement — mais la promesse est comparable à l'offre gratuite des concurrents |
| **3. Captation sur place** | ❌ Non | Hors ligne, mode kiosque, identification de l'animateur |

---

## 2. Le problème à regarder en face

**Le MVP tel que décrit ne contient aucun des éléments qui différencient le projet.**

Reprenons ce que l'étude a établi :

- la création par IA est **commoditisée** — Makeform est entièrement conversationnel, Jotform laisse tester son générateur sans compte, forms.app inclut le créateur IA **dès le plan gratuit** ; **[A]**
- l'hébergement rapide est **standard** chez tous les acteurs ; **[A]**
- la mise à la charte automatique est le **seul élément différenciant du MVP** — elle existe chez Typeform et Jotform mais est verrouillée en Enterprise ou en offres hautes. **[B]**

Donc, sur trois composants du MVP, **deux sont des conditions d'entrée et un seul est un avantage**. Et cet avantage est celui dont l'étude a montré qu'il se démontre très bien mais ne prouve rien sur la conversion.

Résultat : ce MVP est **excellent pour montrer, insuffisant pour vendre**. Face à un prospect qui utilise Tally gratuitement, la seule réponse disponible est « c'est plus joli ».

---

## 3. Ce que ça ne veut pas dire

Ça ne veut pas dire que le MVP est une erreur. Construire d'abord la chaîne logo → charte → formulaire → mise en ligne est un choix technique défendable : c'est la brique la plus incertaine à réaliser, celle qui conditionne tout le reste, et celle qui se démontre en trente secondes.

**Mais il faut nommer ce que c'est : un MVP de démonstration, pas une offre commercialisable.** La confusion entre les deux est ce qui fait perdre six mois.

Conséquence pratique : ne pas le mettre en vente. L'utiliser pour les entretiens — et là il devient très utile, parce que montrer un produit qui marche en fin d'entretien fait parler les gens bien plus qu'une description.

---

## 4. Le complément qui change tout

Pour transformer ce MVP en offre, il manque **un bloc de consentement et un registre horodaté**.

Concrètement :
- une case à cocher non pré-cochée, avec l'identité de l'entreprise et la nature des services — exigences du décret n° 2026-662 ; **[A]**
- l'enregistrement, à chaque soumission, de la date, de l'heure, du texte exact affiché et de la case cochée ;
- une page de consultation et d'export de ce registre ;
- une durée de conservation de trois ans.

**Ce n'est pas un gros développement** au regard de la génération de charte graphique. C'est une table, un horodatage et un export. Et c'est ce qui fait passer le produit de « un formulaire plus joli » à « la seule solution qui vous permet de prouver ».

**Mon avis : c'est le meilleur rapport effort / différenciation de tout le projet.** Je le mettrais dans le MVP plutôt que dans la version suivante.

---

## 5. La décision d'architecture à prendre maintenant

Deux choix sont peu coûteux maintenant et très coûteux plus tard :

**Les espaces de travail.** Si les segments 1 et 2 sont tous deux visés, il faut dès le départ une notion d'espace transférable — un artisan équipé par une agence qui réduit son budget doit pouvoir récupérer ses formulaires, ses pages et son registre sans rien perdre. Rajouter ça ensuite sur une base mono-client est une réécriture.

Ce n'est pas qu'une commodité : quand une agence collecte pour un client, c'est vraisemblablement le client qui est responsable de traitement et l'agence qui est sous-traitante **[?] — à faire confirmer par un juriste**. La preuve appartient donc au client final. La structure de données doit le refléter.

**Le modèle de données de saisie.** Même si le hors ligne n'est pas dans la première version, concevoir la soumission comme un événement horodaté et synchronisable — plutôt que comme une écriture directe en base — laisse la porte ouverte au segment 3 sans surcoût aujourd'hui.

---

## 6. Séquencement proposé

| Phase | Contenu | Objectif |
|---|---|---|
| **0 — maintenant** | Entretiens segments 1 et 2, sans produit | Valider ou tuer la thèse conformité |
| **1 — MVP** | Logo → charte → formulaire → hébergement **+ bloc consentement et registre** | Démontrer et vendre au segment 1 |
| **2** | Multi-comptes, espaces transférables | Rendre le segment 1 réellement exploitable |
| **3** | Page de captation générée | Sortir de la comparaison tarifaire avec Tally |
| **4** | Récupération des leads Meta | Traiter la contradiction 3 ans / 90 jours |
| **5** | Hors ligne, kiosque, animateurs | Segment 3 — **seulement si l'étude 3 le justifie** |

**La phase 0 ne coûte rien et conditionne tout le reste.** Elle peut se faire en parallèle du développement du MVP, mais pas après.
