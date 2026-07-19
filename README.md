# BL dématérialisés — V3 (Lakebase)

Troisième version de la solution, 100 % Lakebase (Postgres managé Databricks) :
métadonnées ET photos en base, aucune dépendance à Unity Catalog, aucun GRANT
admin requis (le créateur du projet Lakebase a tous les droits).

**À déployer sur un NOUVEAU projet Lakebase et deux NOUVELLES apps** (par
exemple `bl-creation-v3` et `bl-administration-v3`) pour ne pas écraser la V2.

## Nouveautés V3

**Modèle de données**
- Numéro de BL **unique** (insensible à la casse) : plus de suffixe -1/-2,
  l'application refuse le doublon avec un message clair.
- Nouvelles tables : `gestionnaires` (préremplie appro 1 → appro 8),
  `portefeuilles` (gestionnaire → fournisseurs, N par gestionnaire),
  `quais` (référentiel géré dans l'app Admin), `base_tiers` (fournisseurs ET
  clients), `base_desadv` avec un sens ACHAT / VENTE.

**App Création**
- Quatre opérations : Nouvelle réception, Nouvelle expédition, Archivage d'un
  ancien BL réception, Archivage d'un ancien BL expédition.
  - Nouvelle expédition : date, plage horaire, quai et commentaire comme une
    réception (sans l'état OK/EDI NOK).
  - Archivages : numéro, date et tiers uniquement.
- DESADV consulté dans le bon sens (achat pour les réceptions, vente pour les
  expéditions) ; libellé Client/Fournisseur selon l'opération.
- Libellés : bouton de capture « 📷 Scanner une page du BL », action
  « 📎 Attacher au BL ».

**App Administration — expérience « model-driven »**
- Navigation latérale par modules : **Achat** (BL réception, DESADV achat,
  Fournisseurs), **Vente** (BL expédition, DESADV vente, Clients),
  **Gestion** (Gestionnaires, Portefeuilles, Quais).
- Ruban d'actions contextuel au-dessus de chaque grille.
- Vues BL : grande grille avec cases à cocher pour les actions de masse
  (passer à OK + email, supprimer, restaurer), fiche de modification en boîte
  de dialogue avec aperçu des pages. 50 lignes par page, plus de filtre quai.
- Vues référentiels : grille éditable (ajout / modification / suppression de
  lignes) + bouton Enregistrer — CRUD complet.

## Déploiement pas à pas

1. **Créer un nouveau projet Lakebase** (UI Databricks → section base de
   données/OLTP → Create project), par exemple `demat-bl-v3`.
2. **Créer les deux apps** : `bl-creation-v3` et `bl-administration-v3`
   (Compute → Apps → Create app, app personnalisée). Sur chacune :
   **Edit → Resources → + Add resource → Database (Lakebase/Postgres)** :
   projet V3, branche `production`, base `databricks_postgres`, permission
   **Can connect and create**, clé `postgres`.
3. **Déployer le code** : dossier Git (ou upload) puis Deploy en pointant
   `src/app_creation` / `src/app_administration` de CE dossier (`v3`).
   Les variables PG* sont injectées par la ressource ; le mot de passe est le
   jeton OAuth du service principal, généré par le code.
4. **Créer les tables et les droits** : récupérer le client ID du service
   principal de chaque app (onglet Authorization), remplacer
   `<SP_APP_CREATION>` / `<SP_APP_ADMINISTRATION>` dans
   `sql/init_lakebase.sql`, décommenter les GRANT, puis exécuter le script
   dans l'**éditeur SQL du projet Lakebase V3** (pas l'éditeur Spark).
5. **Tester** : `BL-2026-0001` auto-remplit le fournisseur FRN1 (DESADV achat
   d'exemple), `EXP-2026-0001` auto-remplit CLIENT ALPHA en expédition.
   Optionnel : `sql/seed_fake_bl.sql` insère 30 BL fictifs avec photos.
6. **Email EDI NOK → OK** : configurer le SMTP dans
   `src/app_administration/app.yaml` (mot de passe via secret).

## Notes d'exploitation

- Jeton OAuth renouvelé avant expiration (45 min) ; requêtes rejouées sur
  coupure (réveil scale-to-zero compris).
- Photos ≤ 2 Mo/page (compression automatique, HEIC accepté, correction de
  perspective débrayable).
- `shared/bl_core` est la source de vérité du code partagé : après
  modification, exécuter `tools/sync_shared.ps1`.
