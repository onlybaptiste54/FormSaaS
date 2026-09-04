# Business plan — Pilotage interne du lancement

*Version 2 — révisée le 3 septembre 2026, après l'entrée en vigueur de la loi opt-in.*

*Document de pilotage, à mettre à jour tous les mois avec les vrais chiffres. Toutes les hypothèses chiffrées ci-dessous sont des points de départ raisonnables à corriger dès les premières données réelles (marquées ⚠️). Le journal des révisions est en section 11.*

---

## 1. Rappel du projet en une page

- **Produit** : plateforme de création de formulaires conformes RGPD/opt-in, pensée pour artisans, BTP, indépendants, commerciaux terrain BtoC et agences de communication locales.
- **Différenciant** : conformité opt-in native et **preuve de consentement opposable**, création rapide (IA + éditeur visuel), gestion d'équipe patron/salariés native, tout-en-un sans couture (création → publication → stats → export, même interface).
- **État du marché** : la bascule du démarchage téléphonique BtoC en opt-in **est en vigueur depuis le 11 août 2026**. Ce n'est plus une échéance à anticiper, c'est une situation d'infraction en cours pour une grande partie de la cible.
- **Cible prioritaire de lancement** : agences de communication locales (effet multiplicateur, elles équipent plusieurs clients artisans/commerçants d'un coup).

**Le changement de récit imposé par le calendrier.** La version 1 de ce document vendait un compte à rebours : « préparez-vous avant août 2026 ». Cet argument est mort. Celui qui le remplace est plus dur et se vend mieux : *« depuis le 11 août, si vous ne pouvez pas prouver le consentement, vous êtes présumé ne l'avoir jamais obtenu. »* On ne vend plus une préparation, on vend une régularisation.

---

## 2. Le cadre légal en vigueur — l'actif central du projet

⚠️ *Section rédigée à partir de sources juridiques secondaires (cabinets d'avocats, publications de la DEETS). Les points marqués d'un astérisque relèvent du décret d'application et **doivent être confirmés sur le texte officiel avant toute utilisation dans une communication commerciale**. Une affirmation juridique fausse sur un site vitrine est un risque en soi.*

### 2.1 Ce que dit le texte

- **Fondement** : article 13 de la loi n° 2025-594 du 30 juin 2025, qui réécrit l'article L223-1 du Code de la consommation. Entrée en vigueur le **11 août 2026**.
- **Bascule opt-out → opt-in** : plus aucun appel commercial vers un particulier sans accord exprès et préalable.
- **Bloctel est supprimé.** Le réflexe « j'ai vérifié Bloctel » ne protège plus personne — c'est un point pédagogique majeur, la plupart des artisans l'ignorent encore.
- **Qualité du consentement** : libre, spécifique, éclairé, univoque et révocable.
- **Charge de la preuve sur le professionnel.** En l'absence de preuve, le consommateur est **présumé n'avoir jamais consenti**.
- **Durée de validité du consentement : un an maximum.** *
- **Conservation de la preuve : trois ans**, présentable en cas de contrôle. *

### 2.2 Ce que ça coûte à celui qui ne s'y conforme pas

| Sanction | Montant | Qui la prononce |
|---|---|---|
| Amende administrative, personne physique | jusqu'à 75 000 € | DGCCRF |
| Amende administrative, personne morale | jusqu'à 375 000 € | DGCCRF |
| **Nullité du contrat** conclu à la suite d'un appel non conforme | perte du chantier | Juge |
| Manquement RGPD sur les données | jusqu'à 4 % du CA mondial ou 20 M€ | CNIL |

La **nullité du contrat** est l'argument qui parle à un artisan, bien plus que l'amende : il ne se projette pas dans un contrôle DGCCRF, mais très bien dans un chantier signé puis annulé. C'est celui-là qu'il faut mettre en avant, pas le montant de l'amende.

À noter également : **la DGCCRF, la CNIL et l'ARCEP partagent désormais les pièces obtenues dans leurs contrôles.** La probabilité de détection augmente mécaniquement.

### 2.3 Le précédent qui rend tout ça concret

Le 15 mai 2025, la CNIL a sanctionné **Solocal Marketing Services d'une amende de 900 000 €** pour avoir démarché des prospects sans consentement valide et transmis leurs données à des partenaires sans base légale — notamment via des **formulaires d'apparence trompeuse**. La sanction s'accompagne d'une injonction de cesser, assortie d'une astreinte de 10 000 € par jour de retard.

C'est le meilleur actif marketing du projet, pour trois raisons : le fautif est un acteur que la cible connaît et pour beaucoup subit ; le délit sanctionné est exactement celui que le produit empêche ; et la décision est publique, datée et citable sans risque.

### 2.4 Ce que la loi impose au registre des consentements — et donc au produit

Les obligations de traçabilité définissent directement le cahier des charges de la fonctionnalité différenciante. Le registre doit permettre de retracer, pour chaque consentement :

| Donnée à conserver | Présente dans l'application aujourd'hui |
|---|---|
| Origine du consentement (formulaire, QR code, stand…) | Partiellement (champ source) |
| Date et heure de collecte | Oui |
| Canal utilisé | Non |
| **Texte exact accepté** par la personne | Oui |
| Biens ou services concernés | Non |
| Identité du professionnel autorisé à appeler | Non |
| Demandes de retrait et leur date | Non |
| **Date d'expiration** (un an après la collecte) | Non |
| Preuve technique (IP, agent utilisateur) | Oui |

**Trois de ces lignes n'existent pas encore et sont bloquantes pour la promesse commerciale.** Elles constituent le cœur de la Phase 1 (section 7).

### 2.5 Deux conséquences stratégiques qu'il ne faut pas rater

1. **Le consentement expire au bout d'un an — donc le besoin est récurrent.** C'est l'argument de rétention le plus solide du produit : un outil qui suit les dates d'expiration et relance la re-collecte au bon moment n'est pas un achat ponctuel, c'est un abonnement justifié. Aucun concurrent généraliste ne fait ça.
2. **Les bases de consentement collectées avant le 11 août 2026 sous l'ancien régime sont largement inexploitables.** Toute la cible a un problème de re-collecte **maintenant**. C'est la fenêtre commerciale, et elle est ouverte aujourd'hui — pas dans six mois.

---

## 3. Modèle économique

### 3.1 Benchmark concurrentiel

**A. Les outils de formulaire** — ce à quoi le produit est comparé fonctionnalité par fonctionnalité.

| Concurrent | Entrée payante | Milieu de gamme | Haut de gamme |
|---|---|---|---|
| **Tally** | Gratuit illimité | Pro ~29 € | Business ~89 € |
| **Typeform** | ~25–29 € | Plus ~49–59 € | Business ~99 € |
| **Jotform** | Bronze ~25 € | Silver ~39 € | Gold ~129 € |
| **Paperform** | ~24 € | — | plus cher |
| **Systeme.io** (FR) | Startup 17–27 € | Webinar 47 € | Illimité 97 € |
| **Google Forms** | Gratuit | — | — |

⚠️ *Tarifs relevés en 2026, en partie libellés en dollars et convertis approximativement. À revérifier avant toute publication comparative.*

**B. Les concurrents de canal** — ce contre quoi le produit se vend réellement auprès d'un artisan. **Cette table manquait à la version 1 et c'est la correction la plus importante de cette section.**

| Acteur | Prix | Ce qu'il vend | Sa faiblesse |
|---|---|---|---|
| **Solocal / PagesJaunes** | ~29 € HT/mois avec engagement, offres de visibilité vers 100 €/mois | Une force de vente téléphonique | Sanctionné par la CNIL, contentieux nourri sur la reconduction tacite, réputation dégradée |
| **Simplébo** | 64 / 114 / 209 €/mois | Un service humain + le partenariat CAPEB | Cher, lent, ~2 000 artisans seulement après 8 ans |
| **Agence locale** | ~6 000 € médians, en une fois | La relation de confiance | Pas de récurrence, pas d'outil, délais en semaines |

Un artisan n'arbitre pas entre Typeform et nous. Il arbitre entre **ne rien faire**, **son agence**, et **le commercial Solocal qui l'a appelé**. Le benchmark A sert à fixer les prix ; le benchmark B sert à construire l'argumentaire.

### 3.2 Grille tarifaire

Inchangée par rapport à la version 1 — elle reste bien calibrée.

| Offre | Cible | Prix mensuel | Prix annuel (mensualisé, −20 %) | Ce qui est inclus |
|---|---|---|---|---|
| **Gratuit** | Test / très petit indépendant | 0 € | 0 € | 1 formulaire actif, 50 leads/mois, 1 test A/B, marque « propulsé par » visible |
| **Solo** | Artisan/indépendant seul | 19 €/mois | 15 €/mois | Formulaires illimités, 1 utilisateur, 1 000 leads/mois, registre de consentement, visualisation de base, tests A/B (5 variantes) |
| **Équipe** | Petite entreprise / commerciaux terrain | 49 €/mois | 39 €/mois | Jusqu'à 5 comptes employés, agrégation multi-formulaires, dashboard patron, export illimité, tests A/B illimités |
| **Agence** | Agence de com multi-clients | 99 €/mois | 79 €/mois | Espaces clients cloisonnés illimités, marque blanche, comptes illimités, comparaison inter-campagnes |
| **Option API/MCP** | Intégrateurs, agences avancées | +29 €/mois | +25 €/mois | API protégée, connecteur MCP, webhooks |

**Un garde-fou tarifaire à ne jamais franchir.** 66 % des TPE françaises consacrent **moins de 300 € par an** à l'ensemble de leur numérique, et cette proportion a augmenté de 6 points en un an. L'offre Solo à 19 €/mois représente 228 € par an : elle passe sous ce plafond, et c'est délibéré. **Solo ne doit jamais dépasser 24 €/mois** (288 €/an) sans changer de motion de vente. L'offre Équipe à 588 €/an franchit le mur, mais elle s'adresse à une structure avec des salariés, pas à un artisan seul — la logique de dépense n'est pas la même.

⚠️ *Le palier Agence peut être poussé vers 129–150 €/mois une fois la valeur confirmée sur les premières agences partenaires. C'est le seul palier où il y a du jeu vers le haut.*

### 3.3 ARPU — correction de la version 1

La version 1 retenait un ARPU de 35 €/mois. Le calcul ne le soutient pas.

| Hypothèse | Calcul | ARPU |
|---|---|---|
| Mix cible (70 % Solo / 25 % Équipe / 5 % Agence), tout en mensuel | 0,70 × 19 + 0,25 × 49 + 0,05 × 99 | **30,50 €** |
| Même mix, tout en annuel (−20 %) | 0,70 × 15 + 0,25 × 39 + 0,05 × 79 | **24,20 €** |
| Mix réaliste : 65 % mensuel / 35 % annuel | 0,65 × 30,50 + 0,35 × 24,20 | **28,30 €** |

**ARPU de pilotage retenu : 28 €/mois.** L'add-on API/MCP, s'il est pris par 3 à 5 % des comptes, ajoute environ 1 €/mois — traité comme un bonus, pas comme une hypothèse.

Conséquence directe : à nombre de clients égal, tous les MRR de la version 1 étaient surestimés d'environ 20 %.

### 3.4 Sources de revenus

1. **Abonnements récurrents** — plus de 90 % du revenu attendu.
2. **Add-on API/MCP** pour les profils techniques et les agences avancées.
3. *(optionnel, non prioritaire)* marketplace de templates sectoriels premium.

---

## 4. Taille de marché — cadrage

⚠️ *Ordres de grandeur pour se donner un cap, pas une étude chiffrée. À affiner avec des données INSEE/CAPEB si un dossier formel devient nécessaire.*

- **TAM** : ~1,9 million d'entreprises artisanales en France, dont **621 803 dans le bâtiment** (97 % du secteur), plus les indépendants de service, les commerciaux terrain et les agences de com locales.
- **SAM** : les structures qui démarchent activement en BtoC ou collectent des leads sur le terrain, et disposent d'un budget outil → **150 000 à 300 000 structures**.
- **SOM à 3 ans** : 1 500 à 3 000 comptes payants, soit 0,5 à 1 % du SAM.

**Le repère de réalité à garder sous les yeux.** Simplébo accompagne un peu plus de **2 000 artisans après huit ans**, avec la CAPEB comme prescripteur, à 768 € l'année minimum. C'est le meilleur point de comparaison disponible sur cette cible. La vente en libre-service est plus rapide qu'une vente accompagnée, donc on peut faire mieux — mais toute projection qui dépasse largement ce repère en deux ans doit être traitée comme une borne haute, pas comme un scénario de base.

---

## 5. Projection financière — 24 mois à partir de septembre 2026

**Hypothèses.** M0 = septembre 2026. Pas de revenu avant le lancement public au M5 (février 2027), parce que la Phase 0 n'a pas encore été faite et que la mise en conformité du produit prend un trimestre (section 7). ARPU 28 €. **Churn mensuel 5 %** — la version 1 mentionnait le churn dans ses KPI mais ne l'appliquait jamais aux projections, ce qui est la principale raison de l'écart entre les deux versions.

### 5.1 Scénario de base

| Échéance | Nouveaux clients/mois | Base clients | MRR |
|---|---|---|---|
| Fin M6 (mars 2027) | 12 | ~20 | ~550 € |
| Fin M12 (sept. 2027) | 40 | ~165 | ~4 600 € |
| Fin M18 (mars 2028) | 70 | ~430 | ~12 000 € |
| Fin M24 (sept. 2028) | 100 | ~785 | ~21 900 € |

### 5.2 Les trois scénarios

| Scénario | M24 clients | M24 MRR | Ce qu'il suppose |
|---|---|---|---|
| **Prudent** (÷1,6) | ~490 | ~13 700 € | Le canal agences ne prend pas ; acquisition portée par le seul SEO |
| **Base** | ~785 | ~21 900 € | Deux à trois canaux fonctionnent correctement |
| **Favorable** (×1,6) | ~1 250 | ~35 000 € | Bouche-à-oreille dans les fédérations + effet régularisation fort |

**À noter franchement : le scénario de base de la version 1 (1 340 clients, 47 000 € de MRR à M24) est devenu le scénario favorable de la version 2.** Il n'était pas absurde, il ne modélisait simplement ni le churn, ni l'ARPU réel, ni la perte du compte à rebours réglementaire.

### 5.3 Le churn fixe le plafond — le calcul qui manquait

À taux d'acquisition constant, la base clients converge vers `nouveaux par mois ÷ taux de churn`. Ce plafond est indépendant du temps et de l'effort commercial.

| Churn mensuel | Base à M24 | **Plafond structurel** à 100 nouveaux/mois |
|---|---|---|
| 3 % | ~890 | **3 300 clients** |
| 5 % (retenu) | ~785 | **2 000 clients** |
| 8 % | ~660 | **1 250 clients** |

Sur 24 mois l'écart reste modéré, parce que la base est jeune. À l'horizon de la cible SOM, il devient décisif : **à 8 % de churn mensuel, l'objectif de 3 000 comptes est mathématiquement hors d'atteinte**, quel que soit le budget marketing. Faire passer le churn de 8 % à 5 % vaut plus que doubler l'acquisition.

C'est aussi ce qui rend le suivi de l'expiration des consentements (section 2.5) stratégique et pas cosmétique : c'est la fonctionnalité qui donne une raison de revenir chaque année.

### 5.4 Seuils de rentabilité

Il n'y a pas un point mort mais trois, selon la rémunération que la structure se verse.

| Seuil | MRR nécessaire | Atteint vers |
|---|---|---|
| Charges fixes seules (hors rémunération) | ~1 500 € | **M8–M9** |
| Un fondateur rémunéré (coût complet ~3 000 €/mois) | ~4 500–5 000 € | **M12–M13** |
| Deux fondateurs rémunérés | ~8 000–9 000 € | **M16** |

La version 1 annonçait un point mort unique à 8 000–12 000 € atteint vers M11–M12 ; c'était en réalité le seuil « deux fondateurs », et il arrive plutôt vers M16 dans le scénario de base.

---

## 6. Structure de coûts

| Poste | Nature | Lancement | À ~400 clients |
|---|---|---|---|
| Hébergement / infrastructure | Fixe, croît avec le volume | 100 – 400 € | 400 – 800 € |
| API IA (génération de formulaires, arbres conditionnels) | Variable | 150 – 600 € | 600 – 1 500 € |
| Outils (support, emailing, analytics, domaine) | Fixe | 100 – 250 € | 250 – 500 € |
| Marketing / acquisition | Investissement à décider | 500 – 2 000 € | 1 500 – 4 000 € |
| Développement produit | Fondateur(s) ou freelance | Variable | Variable |
| Support client | Temps fondateur, puis recrutement | Variable | Poste à prévoir |

**Charges fixes de départ hors rémunération : environ 1 000 à 1 500 €/mois.**

⚠️ *Le poste API IA est le seul qui puisse déraper. Un utilisateur bavard peut coûter plusieurs euros par mois à lui seul. Un plafond d'usage par offre est à poser dès le premier jour payant — pas après le premier mois de facture surprise.*

---

## 7. Roadmap — recalée sur septembre 2026

**Le point de départ réel n'est pas zéro.** Une application fonctionnelle existe déjà : authentification, rôles, entreprise et charte, campagnes, formulaire public, preuve de consentement de base, dashboard, export CSV, données de démonstration. Ce qui manque n'est pas le socle, c'est ce qui tient la promesse commerciale.

### Phase 0 — Preuve du besoin (M0–M1, sept.–oct. 2026)
**C'est le blocage réel : les 5 à 10 entretiens terrain de la version 1 n'ont jamais été faits.**
- 5 agences de communication locales + 5 artisans ou commerciaux qui démarchent en BtoC.
- Question centrale, unique et datée : **« qu'avez-vous changé depuis le 11 août ? »** Les réponses valent plus que dix pages d'analyse.
- **Jalon de sortie** : au moins 6 interlocuteurs sur 10 décrivent un problème de re-collecte ou de preuve. Sinon, le positionnement conformité est à revoir avant d'investir.

### Phase 1 — Combler l'écart de conformité (M2–M3, nov.–déc. 2026)
Le produit promet une preuve opposable ; il ne la fournit pas encore complètement.
- **Registre des consentements exportable** avec les champs manquants de la section 2.4 : canal, biens et services concernés, identité du professionnel autorisé, demandes de retrait.
- **Suivi de l'expiration à un an** et relance de re-collecte. C'est la fonctionnalité de rétention.
- **Politique de conservation à trois ans** documentée et appliquée.
- Remplacement du moteur de génération actuel (correspondance par mots-clés) par un vrai appel à un modèle de langage.
- **Jalon** : un export de registre présentable à un contrôle, validé par un juriste. ⚠️ *Prévoir un budget de relecture juridique — c'est le socle de tout l'argumentaire, il ne peut pas reposer sur des sources secondaires.*

### Phase 2 — Beta fermée (M4, janv. 2027)
- 10 à 20 testeurs recrutés en Phase 0, gratuits contre retours structurés.
- Site vitrine + 3 à 5 articles sur l'angle régularisation, publiés pour commencer à indexer.
- **Jalon** : au moins 60 % des testeurs déclarent qu'ils paieraient.

### Phase 3 — Lancement public (M5–M9, févr.–juin 2027)
- Ouverture avec la grille tarifaire.
- 3 à 5 agences partenaires en offre de lancement.
- Contenu SEO conformité et métier.
- **Jalon** : 100 clients payants, seuil opérationnel franchi.

### Phase 4 — Construction du canal (M10–M15, juil.–déc. 2027)
- CAPEB, FFB, CNATP, chambres de métiers : webinaires et contenu co-brandé.
- 1 à 2 salons professionnels du bâtiment.
- Référencement auprès des dispositifs d'aide régionaux à la numérisation, instruits par les CMA — levier de prix **et** canal de distribution.
- **Jalon** : 40 % des nouveaux clients arrivent par un partenaire.

### Phase 5 — API, MCP et V2 (M16–M24, 2028)
- Add-on API/MCP payant, programme partenaire agences structuré (marque blanche, commissions).
- **Jalon** : ~785 clients payants, ~21 900 € de MRR.

---

## 8. KPIs mensuels

| Indicateur | Pourquoi il compte |
|---|---|
| **MRR et croissance mois/mois** | Le baromètre principal |
| **Nouveaux clients payants / mois** | Vérifie l'acquisition indépendamment du prix moyen |
| **Churn mensuel** | **Le KPI qui fixe le plafond de l'entreprise** (section 5.3). Sous 5 %, idéalement sous 3 % |
| **ARPU réel** | Valide ou corrige l'hypothèse de 28 € — à recalculer chaque mois, pas à supposer |
| **Taux de conversion gratuit → payant** | Valide que l'offre gratuite attire la bonne cible |
| **CAC par canal** | Arbitre où mettre le budget. Repère sectoriel : 50 à 200 € dans l'artisanat |
| **% de clients acquis via une agence partenaire** | Vérifie l'effet multiplicateur, cœur de la stratégie |
| **Formulaires créés / semaine** | Engagement produit ; prédit le churn avant qu'il n'arrive |
| **% de comptes ayant exporté un registre de consentement** | **Nouveau.** Mesure si le différenciant est réellement utilisé ou seulement acheté. Un client qui n'exporte jamais son registre est un client qui partira |
| **% de comptes avec des consentements arrivant à expiration traités** | **Nouveau.** Le mécanisme de rétention fonctionne-t-il vraiment |
| **Taux de complétion moyen des formulaires clients** | Preuve indirecte de qualité, réutilisable en argument commercial |

---

## 9. Risques et mitigations

| Risque | Impact | Mitigation |
|---|---|---|
| **La fenêtre de régularisation se referme** — passé quelques trimestres, la cible s'est arrangée autrement ou a renoncé au démarchage | Perte de l'argument central | Traiter les 12 prochains mois comme la fenêtre utile ; ne pas laisser glisser la Phase 0 |
| **Churn au-delà de 5 %/mois** | Plafonne l'entreprise sous 1 300 comptes quoi qu'il arrive | Prioriser le suivi d'expiration des consentements ; surveiller le churn avant le MRR |
| Cible peu digitale, cycle de vente long | Croissance plus lente que prévu | Passer par les agences, qui vendent à notre place |
| **Un concurrent français sort une brique conformité** (Systeme.io, ou Simplébo qui intègre déjà de l'IA) | Perte de différenciation | Aller vite et associer la marque au sujet avant eux : contenu, partenariats fédérations, cas clients |
| **L'argumentaire juridique s'avère inexact sur un point** | Crédibilité détruite, risque légal propre | Faire relire la page conformité par un juriste avant publication. Non négociable |
| Coût de l'API IA supérieur aux prévisions | Marge dégradée | Plafonner l'usage dans les offres basses dès le premier jour |
| Dépendance à un seul canal | Fragilité | Toujours deux canaux actifs simultanément |
| **Le mur des 300 €/an se resserre encore** | Marché adressable en direct qui rétrécit | Faire de l'agence la cible primaire plutôt que l'artisan direct |

---

## 10. Décisions à prendre maintenant

1. **Lancer les 10 entretiens de la Phase 0 cette semaine.** C'est le seul blocage réel du projet. Tout le reste de ce document est révisable ; ça, non.
2. Confirmer définitivement la cible primaire : agences vs artisans directs. Ce document et l'étude de marché concluent tous deux aux agences.
3. Budgéter la relecture juridique de la Phase 1 — c'est le socle de l'argumentaire, il ne peut pas reposer sur des blogs de cabinets.
4. Fixer un budget mensuel réaliste pour les six premiers mois, pour trancher entre scénario prudent et scénario de base.
5. Décider bootstrap ou financement (BPI, prêt d'honneur). Avec un seuil « un fondateur rémunéré » à M12–M13, la question du revenu personnel d'ici là doit être réglée maintenant.

---

## 11. Journal des révisions

### Version 2 — 3 septembre 2026

| Ce qui a changé | Pourquoi |
|---|---|
| Récit : « préparez-vous » → « régularisez-vous » | La loi est en vigueur depuis le 11 août 2026, l'échéance est derrière nous |
| Nouvelle section 2 : le cadre légal détaillé | La v1 mentionnait l'opt-in sans citer le texte, les sanctions, la nullité des contrats ni l'inversion de la charge de la preuve |
| Ajout de la durée de validité (1 an) et de conservation (3 ans) | Change le produit : le besoin devient récurrent, ce qui justifie l'abonnement |
| Ajout du cahier des charges du registre (2.4) | Trois champs obligatoires manquent dans l'application actuelle |
| Ajout de la sanction CNIL contre Solocal (2.3) | Meilleur actif marketing du dossier, absent de la v1 |
| Nouveau benchmark B : Solocal, Simplébo, agence locale | La v1 ne comparait qu'à des outils de formulaire ; ce ne sont pas les concurrents réels sur la cible artisan |
| ARPU 35 € → **28 €** | Le calcul du mix annoncé donne 30,50 € en mensuel pur, 28,30 € avec 35 % d'annuel |
| Projections divisées par ~1,9 à M24 | Churn désormais modélisé (il ne l'était pas), ARPU corrigé, perte du compte à rebours |
| Nouveau : plafond structurel imposé par le churn (5.3) | Calcul absent de la v1 et déterminant pour la cible SOM |
| Point mort unique → trois seuils (5.4) | Le seuil de la v1 mélangeait charges fixes et rémunération |
| Roadmap recalée sur septembre 2026, Phase 1 redéfinie | Le MVP existe déjà ; ce qui manque, c'est la conformité du registre |
| Garde-fou tarifaire : Solo ≤ 24 €/mois | 66 % des TPE dépensent moins de 300 €/an au total en numérique |
| Deux nouveaux KPI sur l'usage du registre | Mesurent si le différenciant est utilisé, pas seulement acheté |

### Version 1
Version initiale, rédigée avant l'entrée en vigueur de la loi.

---

*Document vivant — à remettre à jour chaque mois avec les vrais chiffres de MRR, churn, ARPU et acquisition dès que l'activité démarre, pour remplacer progressivement les hypothèses ⚠️ par des données réelles.*
