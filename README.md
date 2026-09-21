# Sillage

Sillage est un SaaS français de création et de diffusion de formulaires. Une campagne regroupe les formulaires d’un client, d’un événement ou d’une opération. L’utilisateur décrit chaque formulaire à Luna en langage naturel ; l’application prépare un formulaire court, cohérent avec la marque et conforme aux principes RGPD du cahier des charges.

La documentation stratégique du projet — concept produit, étude de marché et business plan — est dans [`docs/`](docs/README.md).

## Démarrage rapide

Prérequis : Docker Desktop avec Docker Compose v2.

```bash
docker compose up --build
```

Puis ouvrir [http://localhost:3000](http://localhost:3000).

Compte de démonstration :

- Email : `demo@sillage.fr`
- Mot de passe : `demo1234`

L’API et sa documentation interactive sont disponibles sur [http://localhost:8000/api/docs](http://localhost:8000/api/docs).

Pour arrêter l’application :

```bash
docker compose down
```

Les données PostgreSQL restent dans le volume `sillage_postgres_data`. Pour repartir de zéro, utiliser explicitement `docker compose down -v`.

Le schéma est créé et repris au démarrage par `initialize_schema()`, sous verrou d’avis PostgreSQL. Une base antérieure à la séparation campagne / formulaire est migrée une seule fois : chaque campagne devient un dossier plus un formulaire qui **garde son identifiant et son slug**, les réponses et l’historique sont rattachés au formulaire, puis les colonnes devenues inutiles sont supprimées dans la même transaction. Les liens publics déjà diffusés, les réponses collectées et les exports restent valides.

## Fonctionnalités livrées

- Connexion sécurisée par jeton et rôles préparés côté données
- Profil de marque : logo, palette, police, ton et règles, déduits d’une charte importée puis validés
- Création par brief avec Luna via l’API OpenAI Responses et sortie structurée, contexte et images de référence
- Un seul moteur de rendu pour l’éditeur, le formulaire public et les vignettes : l’aperçu est le formulaire
- Modification par opérations : Luna renvoie quelques changements typés, le serveur les applique et les vérifie
- Sélection au rectangle dans l’éditeur, capture automatique de la zone avec son vrai fond
- Édition directe des textes au double-clic, sans passer par l’IA
- Brouillon séparé du formulaire en ligne, historique des versions et annulation par étape
- Garde-fous serveur : 5 champs métier, identifiants et types conservés, contraste WCAG 4,5:1, tunnel intouchable
- Trois niveaux : la campagne regroupe des formulaires, le formulaire porte le statut, le lien et les réponses
- Bilan par campagne : nombre de formulaires, visites, conversion, meilleur formulaire et activité sur 7 jours
- Gestion des formulaires : statut, visibilité, duplication, archivage et restauration
- Formulaire public responsive, validation par champ, pré-remplissage et suivi par canal (`?source=`)
- Consentement explicite non pré-coché, avec preuve : texte, date, IP et user-agent
- Page de remerciement, bouton ou redirection, aperçu dans l’éditeur
- Dashboard : campagnes, formulaires en ligne, activité, sources, conversion et réponses récentes
- Boîte de réception transverse : filtres campagne, formulaire, source et période, recherche plein texte, détail avec preuve de consentement et export CSV UTF-8
- Bibliothèque : sélection Sillage, collection d’entreprise, aperçus en rendu réel et choix de la campagne d’accueil
- Diffusion : liens suivis par canal et code d’intégration à copier
- Données de démonstration réalistes injectées au premier lancement

## Architecture

```text
frontend/  Next.js 15, React 19, TypeScript, CSS natif
backend/   FastAPI, SQLAlchemy, PostgreSQL
compose.yaml  3 services légers avec images Alpine/slim et healthchecks
```

Le front est construit en mode `standalone` puis copié dans une image d’exécution minimale. L’API tourne sans privilèges avec deux workers. PostgreSQL n’est pas exposé sur la machine hôte : seuls le web et l’API publient un port.

## Configuration

Copier `.env.example` vers `.env` pour personnaliser les ports, le mot de passe PostgreSQL, `SECRET_KEY` et la clé OpenAI. `OPENAI_API_KEY` reste exclusivement côté API : ne jamais la préfixer par `NEXT_PUBLIC_`, la placer dans le frontend ou la committer.

Variables principales :

| Variable | Valeur locale par défaut |
| --- | --- |
| `WEB_PORT` | `3000` |
| `API_PORT` | `8000` |
| `POSTGRES_DB` | `sillage` |
| `POSTGRES_USER` | `sillage` |
| `POSTGRES_PASSWORD` | `sillage_dev` |
| `SECRET_KEY` | clé de développement à remplacer |
| `OPENAI_API_KEY` | vide : Luna utilise le générateur local |
| `OPENAI_MODEL` | `gpt-5.4-mini` |
| `OPENAI_TIMEOUT_SECONDS` | `30` |

Avec une clé configurée, Luna transmet à OpenAI le brief de campagne, le contenu du formulaire vide, les six derniers échanges de la conversation, et l’identité publique de la marque : nom commercial, secteur, ton, couleurs et profil de marque (palette, police, règles). Lors d’une modification visuelle, la capture PNG de la zone encadrée est jointe. Les images de charte déposées dans les paramètres et les images de référence ajoutées à un brief sont envoyées au moment de l’analyse, puis oubliées : elles ne sont pas stockées. Le SIRET, l’adresse, le contact DPO et les réponses des prospects ne sont jamais transmis. Les requêtes utilisent `store: false`. Une clé invalide ou une indisponibilité OpenAI produit une erreur explicite ; le mode local est utilisé uniquement pour la création lorsqu’aucune clé n’est configurée.

## Développement sans Docker

Backend :

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Sans `DATABASE_URL`, l’API utilise SQLite pour simplifier le développement local.

Frontend :

```bash
cd frontend
pnpm install
pnpm dev
```

## Vérifications

```bash
cd backend && pytest -q
cd frontend && pnpm build
docker compose config
```

## Suite produit recommandée

Les interfaces sont prêtes à accueillir les autres briques plus lourdes du cahier des charges : WebSocket temps réel, QR codes dynamiques, exports PDF/XLSX, webhooks, synchronisation Google Sheets, PWA hors-ligne et serveur MCP. Elles n’ont volontairement pas été simulées par de faux connecteurs.

Côté produit, les suites naturelles sont la fusion des onglets Tunnel et Remerciement, une page Marque dédiée, des variantes A/B arbitrées par la conversion, et un mode « une question par écran » pour le formulaire public.
