# Documentation stratégique — Sillage

Documentation produit et business de **Sillage**, le SaaS de formulaires conformes RGPD/opt-in pour artisans, BTP, indépendants, commerciaux terrain BtoC et agences de communication locales.

Aucun code ici : concept, marché, business. Le code de l'application est à la racine du dépôt (`backend/`, `frontend/`), documenté dans le [README principal](../README.md).

## Contenu

| Fichier | Ce qu'il contient |
|---|---|
| [concept-saas-formulaires-france.md](concept-saas-formulaires-france.md) | Le concept produit complet : étude de marché, concurrents, personas, cas d'usage (centre laser), 4 piliers de différenciation, fonctionnalités (dont le Formulaire intelligent / tunnel guidé, la sélection à la souris, les tests A/B), sécurité/API/MCP, mots-clés SEO et stratégie marketing. |
| [business-plan-pilotage-interne.md](business-plan-pilotage-interne.md) | **Version 2 (3 septembre 2026).** Cadre légal détaillé de la loi opt-in en vigueur, grille tarifaire benchmarkée, ARPU, projections MRR sur 24 mois en 3 scénarios avec churn modélisé, plafond structurel imposé par le churn, 3 seuils de rentabilité, structure de coûts, roadmap en 6 phases recalée sur septembre 2026, 11 KPIs mensuels, 8 risques et le journal des révisions. |

## Périmètre — un dépôt, un produit

La décision de séparer les deux produits est actée :

- **Sillage** (formulaires conformes) → ce dépôt, et ces documents.
- **Devanture** (site vitrine piloté par IA, nom de code provisoire) → produit distinct, dépôt distinct. Sa spécification et son étude de marché vivent hors de ce dépôt, sous forme de pages publiées.

Ne pas mélanger les deux ici : les cibles se recoupent, mais le marché, le vocabulaire et la concurrence ne sont pas les mêmes.

## Idées clés à ne pas perdre de vue

- **La loi est en vigueur.** Depuis le **11 août 2026** (loi n° 2025-594 du 30 juin 2025, art. 13), le démarchage téléphonique BtoC exige un consentement préalable. Bloctel est supprimé. On ne vend plus une préparation, on vend une **régularisation**.
- **Sans preuve, pas de consentement.** La charge de la preuve pèse sur le professionnel : en son absence, le consommateur est présumé n'avoir jamais consenti. C'est la phrase qui vend le produit.
- **Le consentement expire au bout d'un an**, et la preuve se conserve trois ans. Le besoin est donc *récurrent* — c'est ce qui justifie un abonnement plutôt qu'un achat ponctuel. *(À confirmer sur le texte du décret avant toute communication publique.)*
- **Le précédent Solocal** : 900 000 € d'amende CNIL le 15 mai 2025, pour prospection sans consentement via des formulaires d'apparence trompeuse. Le meilleur actif marketing du dossier.
- **Positionnement** : « conforme par défaut » + « beau et rapide, pas compliqué » + « fait pour le terrain français » + « tout-en-un sans couture ».
- **Cible de lancement prioritaire** : les agences de communication locales (effet multiplicateur).
- **Fonctionnalité phare** : le Formulaire intelligent (tunnel guidé) avec arbre de questions généré par l'IA.
- **Garde-fou tarifaire** : 66 % des TPE dépensent moins de 300 € par an en numérique. L'offre Solo ne doit jamais dépasser 24 €/mois.
- **Le churn fixe le plafond de l'entreprise.** À 8 % par mois, la base plafonne sous 1 300 comptes quelle que soit l'acquisition. À surveiller avant le MRR.

## Le blocage réel

Les **5 à 10 entretiens terrain** de la Phase 0 n'ont toujours pas été menés. Tout le reste de la documentation est révisable ; ça, non. Question centrale à poser : *« qu'avez-vous changé depuis le 11 août ? »*

## Pas encore rédigé

- Site vitrine : structure des pages + accroches SEO conformité.
- Naming du produit (« Sillage » est le nom de l'application, pas nécessairement le nom commercial).
- Cahier des charges produit détaillé du MVP conformité (registre exportable, suivi d'expiration, rétention trois ans).
- Modèle financier chiffré une fois la cible primaire définitivement arrêtée.

---

*Documents vivants — à mettre à jour au fil du projet. Le business plan porte un journal des révisions ; le tenir à jour à chaque modification.*
