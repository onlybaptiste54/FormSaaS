# Documentation stratégique — Sillage

Documentation produit et business historique de **Sillage**. Le produit inclut désormais un parcours dédié aux tunnels de vente guidés par Luna ; voir le [README principal](../README.md) pour le fonctionnement actuel.

**Décision produit du 27 octobre 2026 :** la priorité de développement est le tunnel de vente (pages de découverte et d'offre, action externe, publication et statistiques liées au parcours). Les formulaires existants restent disponibles. Les sections ci-dessous conservent le raisonnement antérieur centré sur les formulaires ; elles ne décrivent plus la priorité actuelle.

Aucun code ici : concept, marché, business. Le code de l'application est à la racine du dépôt (`backend/`, `frontend/`), documenté dans le [README principal](../README.md).

---

## Direction produit — le formulaire d'abord, les landing pages ensuite

**On construit le formulaire en premier. On ajoute ensuite la génération de landing pages par-dessus le même socle.** Dans cet ordre, jamais l'inverse.

Les quatre raisons de cet ordre :

1. **La valeur défendable est dans le formulaire.** C'est lui qui porte le consentement, le registre horodaté et la preuve. La page, elle, est un habillage — précieux commercialement, mais pas opposable juridiquement.
2. **La charte graphique sert les deux.** Une fois qu'on sait habiller un formulaire aux couleurs d'une marque à partir de son logo, habiller une page est le même mécanisme appliqué à plus de blocs. Le travail n'est pas à refaire, il est à étendre.
3. **La page est ce qui sort de la comparaison tarifaire.** Tant qu'on ne vend qu'un formulaire, on est comparé à Tally et forms.app, qui sont gratuits. Dès qu'on livre la page de captation complète, la comparaison n'a plus lieu. C'est la phase 3 de la [note d'arbitrage](etudes-de-marche/note-arbitrage-mvp.md).
4. **L'ordre inverse produirait un produit inutilisable à mi-parcours.** Une page sans formulaire ne sert à rien à cette cible ; un formulaire sans page se vend déjà.

### Ce que ça impose techniquement

Pour que l'ajout des pages reste **facile** plutôt que d'être une réécriture, une seule règle : **la page doit être le même objet que le formulaire, avec des blocs en plus.** Le formulaire est un bloc de la page, pas un produit voisin. Un moteur de rendu, un modèle de données, une charte compilée en variables — partagés par les deux.

Deux décisions à ne pas repousser, peu coûteuses maintenant et très coûteuses plus tard (voir §5 de la note d'arbitrage) :

- **Les espaces de travail transférables** — un artisan équipé par une agence doit pouvoir repartir avec ses formulaires, ses pages et son registre.
- **La soumission conçue comme un événement horodaté et synchronisable**, plutôt qu'une écriture directe en base. C'est ce qui laisse la porte ouverte au hors-ligne sans surcoût aujourd'hui.

---

## Périmètre — un seul produit

**Décision révisée le 29 septembre 2026.** Le projet a un temps envisagé deux produits séparés : un pour les formulaires, un autre pour les pages, avec deux dépôts. **Ce n'est plus le cas.** Les landing pages sont une extension de ce produit, séquencée après le formulaire — pas un produit voisin. Toute la documentation ci-dessous décrit un seul et même produit.

---

## Contenu

### Cadrage produit et business

| Fichier | Ce qu'il contient |
|---|---|
| [concept-saas-formulaires-france.md](concept-saas-formulaires-france.md) | Le concept produit complet : concurrents, personas (dont agences marketing et responsables marketing internes), cas d'usage du centre laser, 4 piliers de différenciation, fonctionnalités (Formulaire intelligent en tunnel guidé, sélection à la souris, tests A/B), sécurité/API/MCP, mots-clés SEO et stratégie marketing. |
| [business-plan-pilotage-interne.md](business-plan-pilotage-interne.md) | Cadre légal, grille tarifaire, ARPU, projections MRR sur 24 mois en 3 scénarios avec churn modélisé, plafond structurel imposé par le churn, 3 seuils de rentabilité, structure de coûts, roadmap, 11 KPIs mensuels, 8 risques, journal des révisions. **Antérieur aux études de marché ci-dessous : en cas de désaccord, les études font foi.** |

### Études de marché — septembre 2026

Trois segments étudiés séparément avec la même méthodologie (offre / demande / environnement / stratégie), plus une note d'arbitrage. Les sources y sont notées par niveau de fiabilité : **[A]** source primaire, **[B]** recoupé, **[C]** benchmark d'agence, **[?]** hypothèse. **Respecter ces marqueurs : ne jamais citer un [C] ou un [?] en clientèle.**

| Fichier | Segment | Verdict |
|---|---|---|
| [etude-1-agences.md](etudes-de-marche/etude-1-agences.md) | Agences marketing et media buyers | **Segment prioritaire.** Moins de ventes, chacune vaut plus cher, et il devient le canal vers le segment 2. Risque principal : l'étroitesse du marché, à chiffrer. |
| [etude-2-tpe-directes.md](etudes-de-marche/etude-2-tpe-directes.md) | TPE, artisans et commerçants en direct | **À servir, pas à cibler en premier.** Revenu faible, support élevé, résiliation fréquente. Ils prennent ce que le segment 1 a permis de construire. |
| [etude-3-captation-sur-place.md](etudes-de-marche/etude-3-captation-sur-place.md) | Captation physique : stands, galeries, foires | **Meilleur argument, pire niveau de connaissance.** Le canal le plus exposé juridiquement, et celui dont on ne sait ni la taille, ni les acteurs, ni les budgets. Ne rien développer avant d'avoir fait le terrain. |
| [note-arbitrage-mvp.md](etudes-de-marche/note-arbitrage-mvp.md) | — | **Le MVP annoncé est excellent pour montrer, insuffisant pour vendre.** Séquencement en 6 phases, et les deux décisions d'architecture à prendre maintenant. |

---

## Idées clés à ne pas perdre de vue

### Le cadre légal, qui est l'actif central

- **La loi est en vigueur** depuis le **11 août 2026** (loi n° 2025-594 du 30 juin 2025, art. 13) : le démarchage téléphonique BtoC exige un consentement préalable. Bloctel est supprimé. On ne vend plus une préparation, on vend une **régularisation**.
- **Le décret n° 2026-662 du 23 juillet 2026** précise les obligations **[A — CNIL]** : la demande doit comporter l'identité de l'appelant et la nature des biens ou services ; le consentement est **valable un an** ; le retrait doit être possible ; la **preuve se conserve au moins trois ans sur support durable, accessible gratuitement à la personne**. Case pré-cochée interdite.
- **Sans preuve, pas de consentement.** La charge pèse sur le professionnel. C'est la phrase qui vend le produit.
- **Un formulaire type ne vaut pas preuve** — c'est le formulaire individuellement rempli et horodaté qui fait foi. Cela condamne le coupon papier et le Google Forms bricolé.
- **Le précédent Solocal** : 900 000 € d'amende CNIL le 15 mai 2025, pour démarchage sans consentement et transmission à des partenaires sans base légale. **[A]**
- **Une agence qui collecte pour un client est vraisemblablement sous-traitante**, le client étant responsable de traitement. La preuve appartient donc au client final, et la structure de données doit le refléter. **[?] — à faire confirmer par un juriste.**

### Ce que le marché apprend sur le prix

- **Le formulaire est gratuit ; ce qui se paie, c'est la marque.** Chez forms.app, Tally et Makeform, le premier palier payant débloque le retrait du logo de l'éditeur et le domaine personnalisé, pas de la fonctionnalité. **[A]** C'est une disposition à payer observée, pas supposée.
- **La mise à la charte automatique est verrouillée en haut de gamme** : Enterprise chez Jotform, Plus et au-dessus chez Typeform. **[B]** Personne ne la livre à une entreprise qui paie 20 à 30 € par mois. **C'est le créneau.**
- **Segment TPE : plafond réel autour de 25 €/mois.** Au-delà, le prospect compare spontanément à Tally Pro et forms.app Basic.
- **Segment agences : il n'y a plus de plafond.** Une agence ne compare pas à Tally, elle compare au temps de ses équipes et à ce qu'elle refacture. Facturer **par espace de travail, avec palier au nombre de comptes clients — jamais par utilisateur.** Kizeo démontre le problème avec ses 25 € HT/mois/utilisateur. **[A]**

### Les concurrents réels, qui ne sont pas ceux qu'on croit

- **Un media buyer n'ouvre pas Jotform.** Ses outils sont Meta Instant Forms, LinkedIn Lead Gen Forms, et du Zapier vers Google Sheets.
- **Meta Instant Forms retient les leads 90 jours [B], contre trois ans d'obligation légale.** C'est la contradiction la plus exploitable du dossier. Stratégie : **ne pas concurrencer l'Instant Form, s'y brancher** — Meta capte, on récupère, on centralise, on archive la preuve. Se positionner en aval, pas en face.
- **Kizeo Forms est un concurrent frontal sur la captation sur place** (hors ligne, multi-utilisateurs, hébergé en France). **[A]** Sa tarification par utilisateur est sa faille pour un prestataire à vingt animateurs saisonniers.
- **Le SEO frontal est perdu d'avance** face à Jotform, installé depuis des années.

### Ce qu'on ne peut pas prouver — à ne pas citer

- **Aucune étude sérieuse n'isole l'effet de la mise à la charte d'un formulaire sur sa conversion. [?]** Les chiffres du type « 75 % des consommateurs jugent la crédibilité sur le design » sont des reformulations approximatives de travaux anciens. **Ne pas les utiliser en clientèle. [C]**
- Les écarts de coût par lead entre formulaire natif et page hébergée circulent de blog en blog sans source. **[C]**

---

## Le blocage réel

Les **entretiens terrain** n'ont toujours pas été menés. C'est la phase 0 de la note d'arbitrage, elle ne coûte rien, et elle conditionne tout le reste. Tout ce qui est écrit ici est révisable ; ça, non.

Trois règles de conduite d'entretien, issues des études : **demander des faits passés et jamais des opinions sur l'avenir**, **ne pas présenter le produit avant la fin**, et **faire montrer l'écran** plutôt que faire décrire.

Deux seuils de décision sont déjà posés :

- **Segment 1, question 7** (« une heure gagnée par client : plus de clients, ou plus de marge ? »). « Plus de marge » → l'agence achète. « Plus de clients » → elle distribue. Ça tranche le modèle économique.
- **Segment 2** : sur 10 entretiens avec des métiers qui rappellent leurs prospects, moins de 3 avec une trace exploitable du consentement → la thèse conformité tient. Plus de 7 → revenir à la charte graphique comme promesse principale.

---

## Pas encore rédigé

- **Le nombre d'agences françaises réellement adressables** — première donnée à aller chercher, via l'Annuaire des entreprises sur les codes NAF publicité et conseil. Sans elle, le segment prioritaire n'a pas de taille.
- **Le segment 3 dans son entier** : nombre de prestataires d'animation commerciale, volumes, budgets, qui est responsable de traitement.
- Site vitrine : structure des pages et accroches SEO conformité.
- Naming commercial (« Sillage » est le nom de l'application).
- Cahier des charges du MVP conformité : bloc de consentement, registre horodaté exportable, rétention trois ans.
- Modèle financier chiffré, une fois le segment 1 dimensionné.

---

*Documents vivants — à mettre à jour au fil du projet. Le business plan porte un journal des révisions ; le tenir à jour à chaque modification.*
