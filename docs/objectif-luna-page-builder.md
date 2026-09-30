# Objectif : Luna écrit la page

> Document de cadrage destiné à l'agent qui implémente. Il remplace la règle
> actuelle « Luna ne touche qu'à un squelette figé, avec des valeurs validées ».
> Tout ce qui, dans le code ou dans les instructions du modèle, affirme le
> contraire doit disparaître.

## 1. La cible en une phrase

Luna écrit le HTML et le CSS de la page, comme une IA à qui on demande un site
vitrine. L'utilisateur voit le résultat en direct, encadre une zone à la souris
pour dire où il veut un changement, et Luna réécrit. Plusieurs pages
s'enchaînent en tunnel, chacune avec ses statistiques, et le tunnel entier se
diffuse par lien ou par intégration.

Le modèle mental est celui d'un artefact Claude : **une demande, une page
réécrite**. Il n'y a pas d'édition chirurgicale élément par élément, et c'est
assumé.

## 2. Ce que ça change par rapport à l'existant

| Aujourd'hui | Cible |
| --- | --- |
| Squelette figé : marque, en-tête, champs, bouton, note, pied | **HTML libre** écrit par Luna |
| Design réduit à 4 axes + un thème de valeurs bornées | **CSS libre** écrit par Luna |
| Luna renvoie des opérations typées appliquées par le serveur | Luna renvoie **la page** |
| Un rendu React qui interprète un modèle de données | Un **document servi**, isolé dans une iframe |
| Une campagne contient des formulaires | Une campagne contient des **tunnels**, un tunnel contient des **pages** |
| Remerciement = écran terminal unique, réglé dans l'onglet Tunnel | N'importe quelle page en appelle une autre, et **Luna peut le décider** |
| Statistiques par formulaire | Statistiques **par page et par étape** |

**Code qui disparaît** : `backend/app/luna_ops.py` en quasi-totalité,
`frontend/lib/form-design.ts`, `frontend/components/form-renderer.tsx`, et les
règles de `frontend/app/globals.css` qui habillent le formulaire. Une bonne
partie des bugs relevés en §7 s'évapore avec.

## 3. Modèle de données cible

```
Campaign                  le dossier : un client, un événement, une opération
  └── Tunnel[]            plusieurs par campagne, comparables entre eux
        └── Page[]        ordre explicite
              id, slug, role: "landing" | "form" | "thanks" | "step" | "custom"
              html        # document complet écrit par Luna, assaini au stockage
              next        # page_id | url https | null
              visits, conversions
```

La campagne **reste le dossier** livré par le chantier précédent : elle ne
devient pas un tunnel. Une même campagne porte plusieurs tunnels pour qu'on
puisse les comparer par les chiffres — « le tunnel avec landing convertit à 9 %,
le tunnel lien direct à 4 % ». C'est aussi ce qui permet à une campagne de
continuer à porter deux parcours sans rapport l'un avec l'autre, comme la
campagne de démonstration qui réunit une enquête de satisfaction et un
formulaire de contact.

Une page, c'est **une chaîne de HTML**. Pas d'arbre, pas de thème séparé, pas de
jetons de style : les couleurs, les polices, la mise en page et les animations
vivent dans le `<style>` que Luna écrit dans la page.

### 3.1 Les trois points d'ancrage du produit

Ce sont les seules choses que le HTML doit respecter. Elles ne limitent pas la
création : elles branchent la page sur le reste du SaaS.

1. **Les champs de collecte** sont des `input`, `select`, `textarea` avec un
   attribut `name`. Le serveur extrait ce manifeste du HTML à l'enregistrement :
   c'est lui qui alimente la boîte de réception, les exports et les statistiques.
2. **Le consentement RGPD** : Luna place un `<div data-sillage="consent"></div>`
   où elle veut, et l'habille comme elle veut. Le serveur y injecte au rendu la
   case et le texte légal, qu'elle ne réécrit pas.
3. **L'envoi** : un `<form data-sillage="form">` autour des champs. Le serveur
   branche la soumission, la validation et la redirection vers la page suivante.

### 3.2 Stabilité des identifiants de champs

C'est la seule contrainte dure, et elle porte sur les **données**, pas sur le
design. Des réponses sont déjà rattachées à des noms de champs. À chaque
enregistrement, le serveur compare le manifeste extrait au précédent :

- champ renommé ou supprimé **sans réponse collectée** → on accepte en silence ;
- champ renommé ou supprimé **avec des réponses collectées** → on accepte, mais
  on le signale dans la réponse de l'API et l'interface avertit clairement
  (« 39 réponses étaient rattachées à `email`, elles restent consultables dans
  l'historique »). On n'efface jamais une réponse.

Dans les instructions du modèle : conserver les `name` existants sauf demande
explicite du contraire.

### 3.3 La mesure

Deux mesures distinctes, qui ne passent pas par le même chemin.

**Les réponses** viennent du manifeste du §3.1 : nom, type déduit de la balise et
de `type`, libellé lu dans le `<label for>`, caractère obligatoire lu sur
`required`. C'est lui qui donne à la boîte de réception « Nom » et « Email » au
lieu de clés brutes, et qui alimente les exports.

**L'entonnoir** ne demande aucun script dans la page — ce qui tombe bien,
l'iframe du §4 n'a pas `allow-scripts`. Tout se compte côté serveur :

```
landing     1000 visites   le serveur sert la page
formulaire   300 visites   le bouton de la landing mène ici : la visite EST le clic
merci         90 visites   le serveur enregistre la soumission
```

L'abandon par étape se déduit : `1 − visites(n+1) / visites(n)`.

**Cookie de parcours.** Sans lui, rien ne relie la visite de la page 2 à celle de
la page 1 : un lien de formulaire partagé directement fausse tout l'entonnoir. Un
cookie propriétaire, posé à l'entrée dans le tunnel, porte l'identifiant de
parcours d'étape en étape. Le même objet transporte la `source` que le Lot 4
exige de conserver, et se raccorde au jeton qui permet à la page de merci de
connaître le prénom. Un seul mécanisme pour les trois besoins.

À faire confirmer côté conformité : un cookie de mesure d'audience peut être
exempté de consentement s'il reste strictement statistique, sans recoupement
entre sites et avec une durée limitée.

## 4. Rendu : iframe isolée

La page est servie dans une `<iframe srcdoc>` **même origine**, avec
`sandbox="allow-forms allow-same-origin"` et **sans** `allow-scripts`.

Pourquoi l'iframe plutôt qu'un `innerHTML` dans la page React :

- Le CSS de la page générée ne peut plus atteindre l'interface de Sillage, ni
  l'inverse. Toute une famille de bugs relevés en §7 devient impossible par
  construction — dont le textarea de l'éditeur qui écrit en blanc sur blanc.
- Aucun script ne s'exécute à l'intérieur, quelle que soit la source du HTML.
- Même origine, donc le parent lit et écrit dans le document : il branche la
  soumission du formulaire, injecte le bloc de consentement, et la capture
  d'écran s'exécute sur `iframe.contentDocument.body` sans rien changer à la
  mécanique actuelle.

Même composant pour l'aperçu de l'éditeur, la page publique et les vignettes de
la bibliothèque (vignette = même iframe, non interactive, à l'échelle).

La couche de sélection à la souris reste **par-dessus** l'iframe, dans le parent :
c'est elle qui donne le rectangle et la capture.

## 5. Sécurité : non négociable, et sans effet sur la création

Le HTML est stocké **assaini**, pas seulement affiché assaini :

- liste blanche de balises et d'attributs ; `script`, `iframe`, `object`,
  `embed`, `form[action]` externes et tout attribut `on*` retirés ;
- URL en `https` ou `data:image/*` uniquement, pas de `javascript:` ;
- `<style>` conservé, mais `@import` et `url()` externes filtrés ;
- en-tête CSP sur la page publique.

Ce n'est pas une limite de design : Luna n'a aucun besoin de `script` pour faire
une belle page, et tu sers ces pages sur ton domaine, à des visiteurs qui y
saisissent des données personnelles.

## 6. L'agent

### 6.1 Ce qu'elle renvoie

Sortie structurée à deux champs :

```
{ message: "une phrase en français sur ce qui a été fait",
  html:    "<!doctype html>…"   # la page entière, réécrite }
```

C'est tout. Plus d'opérations, plus de schéma de design.

**La sortie par région est structurelle, pas optionnelle.** Réécrire 800 lignes
de HTML à chaque « mets le bouton en bleu » coûte une vingtaine de secondes, et
c'est le principal défaut de la cible. Luna balise ses régions quand elle écrit
la page (`data-sillage-region="hero"`), et peut ensuite ne renvoyer que l'une
d'elles :

```
{ message: "…", region: "temoignages", html: "<section data-sillage-region=\"temoignages\">…</section>" }
```

Le serveur la recoud dans le document et stocke la page complète en version :
l'annulation du §6.4 ne change pas.

La visée le permet déjà : l'utilisateur encadre une zone, et le mécanisme de
sélection sait résoudre un rectangle en éléments. Il suffit de le faire pointer
sur les `[data-sillage-region]` dans l'iframe pour savoir quelle région est
visée, et le dire à Luna — ce qui améliore aussi la précision de la visée.

Cas particulier à traiter en premier, parce qu'il couvre une grande part des
demandes réelles : « plus d'espace », « le bouton en bleu », « titre plus gros »
ne touchent que le bloc `<style>`. Luna renvoie alors `region: "style"` et
quelques dizaines de tokens.

Deux garde-fous :

- **Une demande globale reprend le chemin complet.** « Rends la page plus
  aérée », « harmonise les couleurs » ne sont pas locales. La région ne
  s'applique que si l'utilisateur a encadré une zone *et* que la demande y est
  circonscrite. Dans le doute, page entière.
- **Le fragment est vérifié** : il doit ouvrir et fermer sur la même balise
  `data-sillage-region`. Sinon on refait une réécriture complète plutôt que de
  recoudre n'importe quoi.

### 6.2 Ce qu'elle doit recevoir

Plusieurs de ces points manquent aujourd'hui, et ça se voit dans la qualité de
ses réponses :

1. **Le brief d'origine.** `backend/app/main.py` le transmet déjà, mais
   `revise_campaign` le perd en reconstruisant l'état, si bien que le test
   `if state.get("brief")` (`backend/app/luna.py:464`) est **toujours faux**.
   Code mort à réparer.
2. **Le HTML courant de la page**, intégralement.
3. **La capture de la zone encadrée** (voir §7) et le rectangle en pourcentages
   de la page, pour qu'elle situe la zone dans le document.
4. **L'historique réel de la conversation.** `luna_history`
   (`backend/app/main.py:237`) prend `form.versions[-6:]` toutes sources
   confondues : une publication et trois corrections manuelles suffisent à vider
   sa mémoire, alors que le fil affiché à l'utilisateur, lui, est complet.
   Filtrer sur les échanges Luna avant de couper.
5. **Les images, persistées.** Ni les captures ni les pièces jointes ne sont
   stockées : elles disparaissent au rechargement et ne repartent jamais dans
   l'historique. « Reprends la couleur de l'image d'avant » est structurellement
   impossible aujourd'hui. Les stocker avec les versions et les retransmettre.
6. **L'identité de marque** (déjà en place) **et les statistiques de la page** :
   visites, conversion, abandon. Elle peut alors proposer des améliorations
   fondées, pas seulement esthétiques.
7. **Les trois points d'ancrage du §3.1** et la liste des `name` déjà utilisés.

### 6.3 Latence et coût

**Le cache d'invite ne résout pas la latence.** Il porte sur ce que le modèle
lit ; les vingt secondes viennent de ce qu'il écrit. Le temps d'une génération
vaut à peu près le nombre de tokens produits divisé par le débit : une page de
800 lignes, c'est de l'ordre de 10 000 tokens en sortie. Relire 10 000 tokens
d'entrée, en cache ou non, coûte une fraction de seconde. Le cache fait
économiser de l'argent, pas du temps.

**Principe directeur : on limite ce que Luna écrit, jamais ce qu'elle lit.** Elle
reçoit toujours la page entière — c'est l'entrée, c'est ce qui est mis en cache,
et c'est ce qui lui permet de réutiliser les classes et les variables CSS
existantes. Rogner l'entrée pour aller plus vite coûterait la qualité.

Cinq leviers, par ordre d'effet :

1. **Sortie par région** (§6.1). De ~10 000 tokens à ~500 sur une retouche
   locale. C'est le levier principal.
2. **Streaming.** L'appel est aujourd'hui bloquant (`backend/app/luna.py:373`
   poste et attend tout). En streaming, le HTML arrive au fil de l'eau et
   l'iframe se peint en direct : premier rendu en une seconde environ, la page
   se construit sous les yeux. Le total ne raccourcit pas, l'attente aveugle
   disparaît — c'est le modèle d'artefact du §1. L'iframe sans `allow-scripts`
   rend l'aperçu progressif sûr même avant assainissement ; on assainit une
   seule fois, à l'enregistrement.
3. **Ne pas réexpédier les images à la reprise.** La boucle de
   `backend/app/luna.py:532` renvoie tout à la deuxième tentative, jusqu'à deux
   fois 30 s. Avec une sortie HTML il n'y a plus d'opérations à valider, donc
   cette boucle disparaît presque entièrement.
4. **Ordonner l'envoi pour le cache.** D'abord le stable (instructions système,
   identité de marque, les trois ancrages), ensuite le volatil (HTML courant,
   instruction, capture). Le cache retient le plus long préfixe commun : une
   instruction placée en tête l'annule.
5. **Plafonner la taille du HTML stocké** et le signaler proprement.

Ordres de grandeur visés :

| Demande | Produit | Cible |
| --- | --- | --- |
| « Le bouton en bleu » | le `<style>` | ~1 s |
| « Rends ce témoignage plus sobre » | une région | ~2–4 s |
| « Ajoute une section tarifs » | une région insérée | ~3–5 s |
| « Fais-moi une landing complète » | la page entière, en streaming | premier rendu ~1 s |

**Écarté pour l'instant : router les petites demandes vers un modèle rapide.**
C'est le seul levier qui coûte en qualité — un modèle rapide sur « rends ce
témoignage plus sobre » peut donner un résultat fade. À reconsidérer plus tard,
et seulement après mesure.

### 6.4 Annulation

Elle survit telle quelle, et c'est gratuit : chaque version stocke déjà un
instantané complet. Une page = une chaîne, donc revenir en arrière consiste à
réécrire la chaîne précédente. Le fil de conversation doit en revanche **marquer
visuellement** les messages annulés, ce qu'il ne fait pas aujourd'hui.

## 7. La capture envoyée à Luna

C'est le seul moyen de visée qui reste, donc elle doit être irréprochable. Trois
défauts cumulés aujourd'hui, tous à corriger :

1. Elle photographie `.editor-selection-layer`, pas l'étage qui porte le fond de
   page : **le dégradé est absent**, l'image arrive sur fond transparent, et en
   repli JPEG le fond devient noir. Sur une page sombre, Luna voit du texte clair
   sur du vide.
2. Le filtre de `frontend/lib/capture.ts` n'exclut que `.selection-rect` : **la
   bulle de l'éditeur est photographiée**, avec son textarea et ses boutons,
   posée par-dessus la zone à analyser.
3. `backdrop-filter` n'est pas rasterisé : les effets de flou n'apparaissent
   jamais.

Avec l'iframe du §4, la capture s'exécute sur le document interne : elle ne peut
plus contenir l'interface de l'éditeur, et le fond est celui de la page. Les
points 1 et 2 disparaissent par construction. Pour le point 3, si le flou reste
incapturable, le décrire en texte dans le contexte plutôt qu'envoyer une image
trompeuse.

Autres correctifs de la capture :

- `frontend/lib/capture.ts:5` compare une longueur de chaîne à des octets : le
  seuil réel est ~2,8 Mo, pas 3,8 ;
- `backend/app/schemas.py` n'impose **aucune limite de taille par image**
  (`images: list[str]` sans `max_length`), plus une capture jusqu'à 4 Mo, le tout
  gardé en mémoire. Le navigateur plafonne, pas le serveur.

## 8. Bugs actuels à traiter

**Bloquants, à corriger immédiatement — ils sont indépendants de la refonte et
un formulaire public tombe aujourd'hui à cause du premier :**

- ~~`backend/app/luna_ops.py:183` écrit `"style": {}` à chaque appel, même pour
  un simple changement de texte. Côté rendu, `frontend/lib/form-design.ts:75` ne
  fusionne pas un style partiel avec les valeurs par défaut (`{}` est truthy) et
  `rgbChannels` lève un `TypeError`.~~ **CORRIGÉ** côté rendu : `normalizeDesign`
  fusionne désormais tout style partiel avec les valeurs par défaut, vérifié en
  injectant un style ne contenant que `accent`. Le backend écrit toujours `{}`,
  mais ça ne casse plus rien et `luna_ops.py` disparaît avec la refonte.
- `validate_state` (`backend/app/luna_ops.py:267`) contrôle le contraste de tout
  l'état alors que `generate_campaign` n'en contrôle aucun à la création : un
  formulaire né avec un style « verre » devient **définitivement non
  modifiable**, même « change le titre » est refusé deux fois puis renvoie un
  503. Ce garde-fou disparaît avec `luna_ops.py` ; en attendant, le neutraliser.

**Interface de l'éditeur** (`frontend/components/luna-form-editor.tsx`), à
conserver et corriger, puisque c'est elle qui porte la visée par capture :

- ~~la bulle est positionnée sans recadrage dans un panneau en
  `overflow:hidden`~~ **CORRIGÉ** : elle est mesurée puis recadrée dans le
  calque, et bascule au-dessus du cadre quand il n'y a plus la place en dessous ;
- ~~le message envoyé et ses images clignotent~~ **CORRIGÉ pour la session en
  cours** : les images envoyées restent attachées à leur version dans le fil.
  Elles disparaissent toujours au rechargement — c'est le point 5 du §6.2, qui
  demande de les persister ;
- le bouton de pièce jointe a été retiré de la bulle : la capture de la zone y
  est déjà, et joindre d'autres images se fait dans le composeur du chat ;
- en cas d'erreur, le texte revient dans le composeur mais la sélection et la
  capture sont déjà perdues ;
- un `mouseup` hors du canevas laisse le glisser armé et `Escape` ne le
  réinitialise pas : passer en pointer capture ;
- les pièces jointes sont partagées entre la bulle et le composeur, et la clé de
  liste collisionne si la même image est jointe deux fois ;
- les refus métier remontent en 503 au lieu de 422.

**Disparaissent avec la refonte, à ne pas corriger** : le halo « modifié » mal
positionné, les règles CSS qui écrasent le thème (`globals.css:330-338`, `:604`,
`:609`), la divergence entre l'onglet Tunnel et le brouillon.

## 9. Migration

Déterministe, sans perte :

1. Chaque `Form` existant devient une `Page` de rôle `form`. Son HTML est produit
   une fois pour toutes par un **gabarit de conversion** qui rejoue le rendu
   actuel (marque, en-tête, champs, bouton, note, pied) avec le style courant, y
   compris les anciens jetons `background` / `radius` que `styleFromLegacy` sait
   déjà convertir. Le résultat doit être visuellement identique à la page
   publique d'aujourd'hui.
2. `thank_you` devient une `Page` de rôle `thanks`, rattachée en `next`.
3. Les `name` des champs sont repris tels quels : les réponses restent
   rattachées.
4. Slugs, réponses, statistiques et versions sont conservés. Prévoir la lecture
   des instantanés à l'ancien format pour que l'historique reste restaurable.

## 10. Découpage en lots livrables

- **Lot 0 — Urgence.** Les deux bloquants du §8. Indépendant du reste, à livrer
  tout de suite.
- **Lot 1 — Le document.** Page en HTML, assainissement, rendu en iframe isolée,
  extraction du manifeste de champs, injection du consentement, branchement de
  la soumission, migration.
- **Lot 2 — L'agent.** Nouvelle sortie `{ message, html }`, sortie par région et
  cas `style` (§6.1), streaming avec rendu progressif, contexte complet du §6.2,
  capture fidèle du §7, persistance des images, instructions système réécrites,
  envoi ordonné pour le cache.
- **Lot 3 — Le tunnel.** Pages multiples, enchaînement, cookie de parcours,
  statistiques par étape (§3.3), jeton pour la personnalisation et la protection
  des étapes, parcours visiteur.
- **Lot 4 — La diffusion.** Lien et intégration d'un tunnel entier, pas d'une
  seule page ; suivi de source conservé d'une étape à l'autre.

## 11. Critères d'acceptation

1. « Fais-moi une page vitrine avec un héros plein écran, trois arguments en
   colonnes, deux témoignages et le formulaire en bas » produit la page demandée
   en une seule demande.
2. Encadrer le deuxième témoignage et écrire « rends-le plus sobre » produit une
   page où seul ce témoignage a visiblement changé — par la qualité de la visée,
   pas par une garantie technique.
3. Ce que la capture montre correspond exactement à ce que l'utilisateur voit,
   fond compris, sans aucune interface de l'éditeur dedans.
4. Dix demandes successives ne provoquent aucune erreur de rendu, ni dans
   l'éditeur ni sur la page publique.
5. Le CSS écrit par Luna, même agressif (`* { display:none }`), n'altère jamais
   l'interface de Sillage autour de l'aperçu.
6. Une page contenant `<script>`, un attribut `onclick` ou une URL
   `javascript:` est stockée neutralisée.
7. Après une réécriture complète de la page, les réponses déjà collectées
   restent consultables et exportables, et tout champ renommé est signalé à
   l'utilisateur.
8. Le consentement RGPD est présent avec son texte serveur sur toute page qui
   collecte, quelle que soit la composition choisie par Luna.
9. Après rechargement, le fil de conversation affiche encore les images
   envoyées, et Luna peut s'y référer au tour suivant.
10. Un retour arrière restaure la page précédente à l'identique et le message
    annulé est marqué comme tel dans le fil.
11. Un tunnel de trois pages se diffuse par un lien unique et une intégration
    unique, et les statistiques montrent l'abandon à chaque étape.
12. « Mets le bouton en bleu » sur une page existante répond en une poignée de
    secondes, sans réécrire la page entière, et ne modifie rien d'autre.
13. Une création de page complète affiche un rendu partiel en environ une
    seconde et se construit progressivement, sans écran d'attente aveugle.
14. Une demande globale (« rends la page plus aérée ») reprend bien le chemin de
    réécriture complète, et le résultat reste cohérent d'une section à l'autre.
