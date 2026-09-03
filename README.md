# Sillage

Sillage est un SaaS français de création et de diffusion de formulaires. L’utilisateur décrit sa campagne à Luna en langage naturel ; l’application prépare un formulaire court, cohérent avec la marque et conforme aux principes RGPD du cahier des charges.

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

## Fonctionnalités livrées

- Connexion sécurisée par jeton et rôles préparés côté données
- Identité d’entreprise : juridique, palette, ton et contact DPO
- Création par prompt avec Luna via l’API OpenAI Responses et sortie structurée
- Génération adaptée aux contacts, sondages, événements et visites de chantier
- Règle MOFU : 5 champs métier maximum, plus consentement
- Gestion des campagnes : statut, visibilité, duplication et archivage
- Formulaire public responsive, pré-remplissage URL possible côté architecture
- Validation des champs et consentement explicite non pré-coché
- Preuve de consentement : texte, date, IP et user-agent
- Page de remerciement et tunnel à option unique
- Dashboard : activité, sources, conversion et réponses récentes
- Tableau des réponses et export CSV UTF-8
- Bibliothèque de points de départ, équipe et paramètres
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

Avec une clé configurée, Luna transmet à OpenAI uniquement le brief de campagne, le nom commercial, le secteur, le ton et les couleurs de marque. Le SIRET, l’adresse, le contact DPO et les réponses des prospects ne sont pas transmis. Les requêtes utilisent `store: false`. Une clé invalide ou une indisponibilité OpenAI produit une erreur explicite ; le mode local est utilisé uniquement lorsqu’aucune clé n’est configurée.

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

Les interfaces sont prêtes à accueillir les autres briques plus lourdes du cahier des charges : WebSocket temps réel, QR codes dynamiques, exports PDF/XLSX, webhooks, synchronisation Google Sheets, PWA hors-ligne et serveur MCP. Elles n’ont volontairement pas été simulées par de faux connecteurs dans ce MVP.
