# Sillage

Sillage aide une entreprise à créer et publier un tunnel de vente guidé. L’utilisateur décrit son offre, son public, ses arguments et l’action finale souhaitée ; Luna génère deux pages aux couleurs de l’entreprise. Sillage mesure les entrées, les passages entre pages et les clics vers le lien externe final. Les formulaires et campagnes historiques restent disponibles.

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

Le schéma est créé et repris au démarrage par `initialize_schema()`, sous verrou d’avis PostgreSQL. Une base antérieure à la séparation campagne / formulaire est migrée une seule fois : chaque campagne devient un dossier plus un formulaire qui **garde son identifiant et son slug**, les réponses et l’historique sont rattachés au formulaire, puis les colonnes devenues inutiles sont supprimées dans la même transaction. La reprise suivante ajoute à chaque formulaire une page HTML et une page de remerciement, puis un tunnel initial qui conserve ces pages. Les réglages de remerciement sont portés par la page du tunnel ; l’ancien champ du formulaire est migré puis conservé vide, avec un alias API pour les clients existants. Les liens publics déjà diffusés, les réponses collectées et les exports restent valides. Une sauvegarde vérifiée reste nécessaire avant toute migration de production.

## Fonctionnalités livrées

- Assistant en trois étapes pour créer un tunnel de vente : offre, arguments et destination de l’action finale
- Deux pages générées par Luna avec le profil de marque, aperçu ordinateur/mobile, retouches en langage naturel, brouillons et versions précédentes
- Publication par lien, mise en pause, correction du lien final et export HTML ZIP du tunnel publié
- Statistiques par tunnel et par période : entrées, passage entre pages, clics finaux, évolution quotidienne et sources (`?source=` ou `?utm_source=`)
- Mesure de parcours sans donnée personnelle : ni adresse IP ni user-agent enregistrés, événements dédupliqués par session et par étape, et oubliés au-delà de treize mois
- Le clic final mène vers une adresse HTTPS externe ; Sillage n’encaisse aucun paiement et ne peut pas confirmer une vente ou réservation externe. L’export HTML fonctionne sans les statistiques Sillage.
- Connexion sécurisée par jeton, tentatives limitées et rôles appliqués sur chaque écriture
- Profil de marque : logo, palette, police, ton et règles, déduits d’une charte importée puis validés
- Création par brief avec Luna via l’API OpenAI Responses : une génération écrit directement le document HTML/CSS complet
- Un document HTML/CSS par page, assaini avant stockage puis rendu dans la même iframe isolée pour l’éditeur, la page publique et les vignettes
- Retouches Luna de page entière, de région ou de bloc CSS, avec aperçu progressif en flux et validation du document avant stockage
- Sélection au rectangle dans l’éditeur, capture automatique de la zone avec son vrai fond
- Captures et images du dialogue persistées avec les versions ; brouillon séparé du document en ligne et retour à une version précédente
- Garde-fous serveur : manifeste des champs extrait du HTML, limites de taille, HTML/CSS filtré, scripts interdits et consentement injecté par le serveur
- Campagne, tunnels et pages ordonnées : étapes visibles dans une liste latérale, création depuis zéro ou depuis une page modèle, aperçu direct et édition avec Luna
- Parcours public protégé par un cookie signé d’une heure ; visites et passages comptés par page, document de remerciement remis après soumission
- Bilan par campagne : nombre de formulaires, visites, conversion, meilleur formulaire et activité sur 7 jours
- Gestion des formulaires : statut, visibilité, duplication, archivage et restauration
- Formulaire public responsive, validation par champ, pré-remplissage et suivi par canal (`?source=`)
- Consentement explicite non pré-coché, avec preuve : texte, date, IP et user-agent
- Page de remerciement configurée depuis sa propre étape, avec bouton ou redirection
- Dashboard : campagnes, formulaires en ligne, activité, sources, conversion et réponses récentes
- Boîte de réception transverse : filtres campagne, formulaire, source et période, recherche plein texte, détail avec preuve de consentement et export CSV UTF-8
- Bibliothèque : sélection Sillage, collection d’entreprise, aperçus en rendu réel et choix de la campagne d’accueil
- Diffusion : liens suivis par canal et code d’intégration à copier
- Données de démonstration réalistes injectées au premier lancement, jamais en production
- Garde-fous d'exploitation : connexion limitée à 10 échecs par quart d'heure et par adresse, collecte publique à 30 envois par dix minutes, parcours public d'un tunnel de vente à 120 appels par dix minutes, un lecteur ne peut rien modifier, les réglages d'entreprise et la suppression d'une réponse restent à un administrateur

## Architecture

```text
frontend/  Next.js 15, React 19, TypeScript, CSS natif
backend/   FastAPI, SQLAlchemy, PostgreSQL
compose.yaml  3 services légers avec images Alpine/slim et healthchecks
```

Le front est construit en mode `standalone` puis copié dans une image d’exécution minimale. L’API tourne sans privilèges avec deux workers. PostgreSQL n’est pas exposé sur la machine hôte : seuls le web et l’API publient un port.

## Configuration

Copier `.env.example` vers `.env` pour personnaliser les ports, le mot de passe PostgreSQL, `SECRET_KEY` et la clé OpenAI.

Avec `ENVIRONMENT=production`, l'API refuse de démarrer tant que `SECRET_KEY` vaut la clé de développement ou fait moins de 32 caractères : cette clé signe les jetons d'authentification **et** le cookie de parcours public, donc une clé connue les rend forgeables. En générer une avec `python -c "import secrets; print(secrets.token_hex(32))"`. Le démarrage rapide ci-dessus reste inchangé : il tourne en `development`.

`OPENAI_API_KEY` reste exclusivement côté API : ne jamais la préfixer par `NEXT_PUBLIC_`, la placer dans le frontend ou la committer.

Variables principales :

| Variable | Valeur locale par défaut |
| --- | --- |
| `ENVIRONMENT` | `development` |
| `WEB_PORT` | `3000` |
| `API_PORT` | `8000` |
| `POSTGRES_DB` | `sillage` |
| `POSTGRES_USER` | `sillage` |
| `POSTGRES_PASSWORD` | `sillage_dev` |
| `SECRET_KEY` | clé de développement, refusée si `ENVIRONMENT=production` |
| `OPENAI_API_KEY` | vide : Luna utilise le générateur local |
| `OPENAI_MODEL` | `gpt-6-luna` |
| `OPENAI_TIMEOUT_SECONDS` | `90` |

Avec une clé configurée, Luna transmet à OpenAI le brief initial, le HTML courant, les six derniers échanges Luna, les captures et images jointes au dialogue, et l’identité publique de la marque : nom commercial, secteur, ton, couleurs et profil de marque. La création d’une page lance une recherche web ciblée ; les retouches peuvent aussi chercher sur le web quand le brief le demande. Le champ facultatif « Site web à consulter » fournit une adresse HTTPS à prendre en compte. Luna doit rendre cliquables les sources des faits qu’elle reprend dans la page. Les images jointes aux retouches restent dans les versions pour conserver la conversation après rechargement. Le SIRET, l’adresse, le contact DPO et les réponses des prospects ne sont jamais transmis. Les requêtes ne stockent pas de contenu chez OpenAI. Une clé invalide ou une indisponibilité OpenAI produit une erreur explicite. Les formulaires historiques gardent leur générateur local sans clé ; la création d’un tunnel de vente avec Luna exige une clé OpenAI.

## Mise en ligne

Un déploiement réel se distingue du développement par une seule variable :

```bash
ENVIRONMENT=production
```

Elle change trois choses :

1. L'API refuse de démarrer tant que `SECRET_KEY` vaut la clé de développement ou fait moins de 32 caractères.
2. Aucune donnée de démonstration n'est créée, donc **le compte `demo@sillage.fr` n'existe pas**. Un compte de démonstration connu annulerait le contrôle des rôles.
3. Au premier démarrage sur une base vide, l'API journalise la commande à lancer pour ouvrir la porte.

Créer le premier administrateur, une seule fois :

```bash
docker compose exec api python -m app.admin --email vous@exemple.fr --company "Votre entreprise"
```

Le mot de passe est demandé sans être affiché ; il doit faire 12 caractères au minimum. Pour un déploiement automatisé, le passer par `ADMIN_PASSWORD` plutôt que par `--password`, qui resterait dans l'historique du shell. La commande crée l'entreprise et son administrateur, et refuse de s'exécuter dès qu'un compte existe : elle ne peut pas servir à s'ajouter à une installation en service. Les membres suivants s'ajouteront par le parcours d'invitation, qui reste à construire.

Deux limites à connaître avant d'ouvrir au public :

- **La limitation de débit est comptée en mémoire, par processus.** L'image lance deux workers, donc les seuils réels sont doublés. Au-delà d'un petit trafic, il faudra un compteur partagé.
- **`X-Forwarded-For` n'est pas lu**, parce qu'une limite qu'un en-tête suffit à contourner n'en est pas une. Derrière un reverse proxy, toutes les requêtes porteraient donc l'adresse du proxy : lancer uvicorn avec `--proxy-headers --forwarded-allow-ips=<adresse du proxy>` le jour où un proxy est ajouté.

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

Côté produit, les suites naturelles sont une page Marque dédiée, des variantes A/B arbitrées par la conversion, et un mode « une question par écran » pour le formulaire public.
