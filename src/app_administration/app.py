"""Application « Administration des BL » — V3.

Expérience structurée type « model-driven » (à la Power Apps) :
  - barre de navigation latérale : modules Achat / Vente / Gestion, vues ;
  - ruban d'actions contextuel au-dessus de la grille ;
  - grande grille de données avec cases à cocher pour les actions de masse
    (vues BL) ou édition directe des lignes (référentiels, CRUD complet) ;
  - fiches de modification et confirmations dans des boîtes de dialogue.
"""

import datetime

import pandas as pd
import streamlit as st

from bl_core import notifications, repository, ui
from bl_core.identity import get_current_user

st.set_page_config(page_title="Administration BL", page_icon="🗂️", layout="wide")

ui.configurer_logs()
ui.injecter_style()

utilisateur = get_current_user()
TAILLE_PAGE = 50
boite_dialogue = getattr(st, "dialog", None) or st.experimental_dialog

MODULES = {
    "Achat": ["BL réception", "DESADV achat", "Fournisseurs"],
    "Vente": ["BL expédition", "DESADV vente", "Clients"],
    "Gestion": ["Gestionnaires", "Portefeuilles", "Quais"],
}
ICONES = {"Achat": "🛒", "Vente": "🚚", "Gestion": "⚙️"}

# =====================================================================
# NAVIGATION LATÉRALE
# =====================================================================
with st.sidebar:
    st.markdown("## 🗂️ Administration BL")
    st.caption("BL dématérialisés · V3")
    module = st.radio("Module", list(MODULES),
                      format_func=lambda m: f"{ICONES[m]} {m}")
    st.divider()
    vue = st.radio("Vues", MODULES[module])
    st.divider()
    st.caption(f"👤 {utilisateur}")

st.markdown(f"### {ICONES[module]} {module} › {vue}")
ui.show_flash()


def _vider_grille(cle: str) -> None:
    st.session_state.pop(cle, None)


# =====================================================================
# BOÎTES DE DIALOGUE (fiche BL, confirmation de suppression)
# =====================================================================
@boite_dialogue("✏️ Fiche du BL")
def dialog_modifier_bl(bl: dict, ids_photos: list[str], cle_grille: str):
    type_op = bl.get("type_operation") or repository.TYPE_RECEPTION
    avec_pq = repository.operation_avec_plage_et_quai(type_op)
    avec_st = repository.operation_avec_statut(type_op)
    tiers_lib = repository.libelle_tiers(type_op)
    type_tiers = (repository.TIERS_CLIENT if type_op in repository.TYPES_VENTE
                  else repository.TIERS_FOURNISSEUR)

    st.caption(f"{repository.LIBELLES_OPERATION.get(type_op, type_op)} · "
               f"saisi par {bl.get('saisie_par') or '?'} le {bl.get('saisie_le') or '?'}")

    with st.form("fiche_bl"):
        numero = st.text_input("Numéro de BL", value=bl["numero_bl"], max_chars=60)
        date_op = st.date_input("Date", value=bl.get("date_reception"))
        tiers_options = repository.lister_tiers(type_tiers)
        index_tiers = (tiers_options.index(bl["nom_fournisseur"])
                       if bl.get("nom_fournisseur") in tiers_options else None)
        nouveau_tiers = st.selectbox(tiers_lib, options=tiers_options, index=index_tiers,
                                     placeholder="Choisir…")
        if avec_pq:
            index_plage = (repository.PLAGES_HORAIRES.index(bl["plage_horaire"])
                           if bl.get("plage_horaire") in repository.PLAGES_HORAIRES else None)
            plage = st.selectbox("Plage horaire", options=repository.PLAGES_HORAIRES,
                                 index=index_plage, placeholder="Non renseignée")
            quais = repository.lister_quais()
            index_quai = quais.index(bl["quai_reception"]) if bl.get("quai_reception") in quais else None
            quai = st.selectbox("Quai", options=quais, index=index_quai, placeholder="Non renseigné")
            commentaire = st.text_area("Commentaire", value=bl.get("comment_bl") or "", max_chars=1000)
        if avec_st:
            statut_choix = st.radio("État de réception", ["OK", "EDI NOK"], horizontal=True,
                                    index=0 if bl.get("statut_bl") == repository.STATUT_OK else 1)

        if st.form_submit_button("💾 Enregistrer", type="primary", use_container_width=True):
            champs = {"numero_bl": numero.strip(), "date_reception": date_op,
                      "nom_fournisseur": nouveau_tiers}
            if avec_pq:
                champs["comment_bl"] = commentaire.strip()
                if plage:
                    champs["plage_horaire"] = plage
                if quai:
                    champs["quai_reception"] = quai
            passe_a_ok = False
            if avec_st:
                champs["statut_bl"] = (repository.STATUT_OK if statut_choix == "OK"
                                       else repository.STATUT_EDI_NOK)
                passe_a_ok = (bl.get("statut_bl") == repository.STATUT_EDI_NOK
                              and champs["statut_bl"] == repository.STATUT_OK)
            try:
                repository.mettre_a_jour_bl(bl["id_bl"], champs, utilisateur)
            except ValueError as e:            # numéro de BL déjà pris
                st.error(str(e))
                st.stop()
            if passe_a_ok:
                envoye = notifications.notifier_passage_ok(
                    numero_bl=champs["numero_bl"], fournisseur=nouveau_tiers,
                    quai=champs.get("quai_reception", ""), date_reception=date_op,
                    utilisateur=utilisateur,
                )
                ui.set_flash("success" if envoye else "warning",
                             f"BL {champs['numero_bl']} mis à jour"
                             + (" — passage à OK notifié par email." if envoye
                                else " — notification email non envoyée (voir les logs)."))
            else:
                ui.set_flash("success", f"BL {champs['numero_bl']} mis à jour.")
            _vider_grille(cle_grille)
            st.rerun()

    if ids_photos:
        with st.expander(f"📎 Pages ({len(ids_photos)})"):
            for i, id_photo in enumerate(ids_photos):
                try:
                    st.image(repository.telecharger_photo(id_photo), caption=f"Page {i + 1}",
                             use_column_width=True)
                except Exception as e:
                    st.caption(f"Page {i + 1} inaccessible : {e}")


@boite_dialogue("🗑️ Confirmation")
def dialog_supprimer_bls(ids: list[str], cle_grille: str):
    st.warning(f"Supprimer logiquement {len(ids)} BL ? Ils resteront restaurables "
               "(case « Inclure les BL supprimés »).")
    col_oui, col_non = st.columns(2)
    if col_oui.button("✅ Confirmer la suppression", type="primary", use_container_width=True):
        for id_bl in ids:
            repository.supprimer_bl(id_bl, utilisateur)
        ui.set_flash("success", f"{len(ids)} BL supprimé(s) logiquement.")
        _vider_grille(cle_grille)
        st.rerun()
    if col_non.button("Annuler", use_container_width=True):
        st.rerun()


# =====================================================================
# VUES « BL » (réception / expédition) — grille + ruban d'actions
# =====================================================================
def vue_bl(nom_vue: str, types: list[str]) -> None:
    avec_statut = repository.TYPE_RECEPTION in types
    tiers_lib = "Client" if types == repository.TYPES_VENTE else "Fournisseur"

    # --- Filtres ---
    with st.expander("🔍 Filtres", expanded=False):
        c1, c2, c3 = st.columns(3)
        f_numero = c1.text_input("Numéro contient", key=f"f_num_{nom_vue}").strip()
        f_tiers = c2.text_input(f"{tiers_lib} contient", key=f"f_frs_{nom_vue}").strip()
        aujourdhui = repository.maintenant_local().date()
        f_dmin = c1.date_input("Du", value=aujourdhui - datetime.timedelta(days=1),
                               key=f"f_dmin_{nom_vue}")
        f_dmax = c2.date_input("Au", value=aujourdhui, key=f"f_dmax_{nom_vue}")
        f_statut = (c3.selectbox("État", ["EDI NOK", "OK", "Tous"], key=f"f_st_{nom_vue}")
                    if avec_statut else "Tous")
        f_suppr = c3.checkbox("Inclure les BL supprimés", key=f"f_sup_{nom_vue}")
    statut = {"OK": repository.STATUT_OK, "EDI NOK": repository.STATUT_EDI_NOK}.get(f_statut)

    # Pagination et sélection réinitialisées quand les filtres changent.
    signature = (f_numero, f_tiers, str(f_dmin), str(f_dmax), f_statut, f_suppr)
    cle_page, cle_grille = f"page_{nom_vue}", f"grille_{nom_vue}"
    if st.session_state.get(f"sig_{nom_vue}") != signature:
        st.session_state[f"sig_{nom_vue}"] = signature
        st.session_state[cle_page] = 1
        _vider_grille(cle_grille)
    page = st.session_state.setdefault(cle_page, 1)

    try:
        df, total = repository.rechercher_bl(
            numero=f_numero, fournisseur=f_tiers, types=types,
            date_min=f_dmin, date_max=f_dmax, statut=statut,
            inclure_supprimes=f_suppr, page=page, page_size=TAILLE_PAGE,
        )
        df = df.reset_index(drop=True)
        photos = repository.photos_pour_bls(df["id_bl"].tolist() if not df.empty else [])
    except Exception as e:
        st.error(f"Erreur de lecture de la base : {e}")
        st.stop()

    ruban = st.container()                     # rempli après la grille (sélection à jour)

    # --- Grille ---
    ids_selection: list[str] = []
    if df.empty:
        st.info("Aucun BL ne correspond aux filtres.")
    else:
        colonnes = {
            "Sélection": [False] * len(df),
            "Numéro": df["numero_bl"],
            "Date": df["date_reception"],
            "Plage": df["plage_horaire"],
            tiers_lib: df["nom_fournisseur"],
            "Quai": df["quai_reception"],
        }
        if avec_statut:
            colonnes["État"] = df["statut_bl"].map(ui.libelle_statut)
        colonnes.update({
            "Opération": df["type_operation"].map(
                lambda t: repository.LIBELLES_OPERATION.get(t, t)),
            "Commentaire": df["comment_bl"],
            "Pages": df["id_bl"].map(lambda i: len(photos.get(i, []))),
            "Saisi par": df["saisie_par"],
            "Saisi le": df["saisie_le"],
            "Supprimé": df["est_supprime"].fillna(False).map(lambda x: "🗑️" if x else ""),
        })
        df_aff = pd.DataFrame(colonnes)
        edite = st.data_editor(
            df_aff, hide_index=True, use_container_width=True, key=cle_grille,
            disabled=[c for c in df_aff.columns if c != "Sélection"],
            column_config={"Sélection": st.column_config.CheckboxColumn("✔", width="small")},
        )
        masque = edite["Sélection"].fillna(False).astype(bool)
        ids_selection = df.loc[masque.values, "id_bl"].tolist()

    # --- Pagination (50 lignes par page) ---
    nb_pages = max((total + TAILLE_PAGE - 1) // TAILLE_PAGE, 1)
    if nb_pages > 1:
        col_prec, col_info, col_suiv = st.columns([1, 2, 1])
        if col_prec.button("⬅️", disabled=page <= 1, key=f"prec_{nom_vue}", use_container_width=True):
            st.session_state[cle_page] -= 1
            _vider_grille(cle_grille)
            st.rerun()
        col_info.markdown(f"<div style='text-align:center'>page {page} / {nb_pages}</div>",
                          unsafe_allow_html=True)
        if col_suiv.button("➡️", disabled=page >= nb_pages, key=f"suiv_{nom_vue}",
                           use_container_width=True):
            st.session_state[cle_page] += 1
            _vider_grille(cle_grille)
            st.rerun()

    # --- Ruban d'actions contextuel ---
    with ruban:
        n = len(ids_selection)
        libelles_boutons = [1.2, 1.2, 1.5, 1.3, 1.3, 3.2] if avec_statut else [1.2, 1.2, 1.3, 1.3, 4.7]
        cols = st.columns(libelles_boutons)
        if cols[0].button("🔄 Actualiser", key=f"act_{nom_vue}", use_container_width=True):
            _vider_grille(cle_grille)
            st.rerun()
        if cols[1].button("✏️ Modifier", key=f"mod_{nom_vue}", disabled=n != 1,
                          use_container_width=True,
                          help="Sélectionnez exactement un BL pour ouvrir sa fiche."):
            ligne = df[df["id_bl"] == ids_selection[0]].iloc[0].to_dict()
            dialog_modifier_bl(ligne, photos.get(ids_selection[0], []), cle_grille)
        decalage = 2
        if avec_statut:
            if cols[2].button("✅ Passer à OK", key=f"ok_{nom_vue}", disabled=n == 0,
                              use_container_width=True,
                              help="Passe les BL EDI NOK sélectionnés à OK (avec notification)."):
                bascules, notifies = 0, 0
                for id_bl in ids_selection:
                    ligne = df[df["id_bl"] == id_bl].iloc[0]
                    if ligne["statut_bl"] != repository.STATUT_EDI_NOK:
                        continue
                    repository.mettre_a_jour_bl(id_bl, {"statut_bl": repository.STATUT_OK}, utilisateur)
                    bascules += 1
                    if notifications.notifier_passage_ok(
                            numero_bl=ligne["numero_bl"], fournisseur=ligne["nom_fournisseur"],
                            quai=ligne["quai_reception"] or "", date_reception=ligne["date_reception"],
                            utilisateur=utilisateur):
                        notifies += 1
                ui.set_flash("success" if bascules else "info",
                             f"{bascules} BL passé(s) à OK, {notifies} notification(s) envoyée(s)."
                             if bascules else "Aucun BL EDI NOK dans la sélection.")
                _vider_grille(cle_grille)
                st.rerun()
            decalage = 3
        if cols[decalage].button("🗑️ Supprimer", key=f"sup_{nom_vue}", disabled=n == 0,
                                 use_container_width=True):
            dialog_supprimer_bls(ids_selection, cle_grille)
        if cols[decalage + 1].button("♻️ Restaurer", key=f"res_{nom_vue}", disabled=n == 0,
                                     use_container_width=True):
            for id_bl in ids_selection:
                repository.restaurer_bl(id_bl, utilisateur)
            ui.set_flash("success", f"{n} BL restauré(s).")
            _vider_grille(cle_grille)
            st.rerun()
        cols[-1].markdown(f"**{total}** BL · **{n}** sélectionné(s)")


# =====================================================================
# VUES « RÉFÉRENTIEL » — grille éditable (CRUD complet)
# =====================================================================
def vue_referentiel(nom_ref: str, nom_vue: str, valeurs_fixes: dict | None = None,
                    config_colonnes: dict | None = None) -> None:
    try:
        df = repository.lire_referentiel(nom_ref, valeurs_fixes)
    except Exception as e:
        st.error(f"Erreur de lecture de la base : {e}")
        st.stop()
    visibles = [c for c in df.columns if c not in (valeurs_fixes or {})]
    df_vis = df[visibles].reset_index(drop=True)
    cle = f"ref_{nom_vue}"

    ruban = st.container()                     # rempli après la grille
    st.caption("Ajoutez une ligne en bas de la grille, modifiez une cellule ou supprimez des "
               "lignes (sélection + touche Suppr), puis cliquez sur **💾 Enregistrer**.")
    edite = st.data_editor(df_vis, num_rows="dynamic", use_container_width=True,
                           key=cle, hide_index=True, column_config=config_colonnes or {})

    with ruban:
        c1, c2, c3 = st.columns([1.6, 1.4, 5])
        if c1.button("💾 Enregistrer", type="primary", key=f"save_{nom_vue}",
                     use_container_width=True):
            try:
                ajouts, suppressions = repository.sauver_referentiel(
                    nom_ref, df_vis, edite, valeurs_fixes)
                if ajouts or suppressions:
                    ui.set_flash("success",
                                 f"{nom_vue} : {ajouts} ajout(s)/modification(s), "
                                 f"{suppressions} suppression(s).")
                else:
                    ui.set_flash("info", "Aucune modification à enregistrer.")
                _vider_grille(cle)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Échec de l'enregistrement : {e}")
        if c2.button("🔄 Actualiser", key=f"refresh_{nom_vue}", use_container_width=True):
            _vider_grille(cle)
            st.rerun()
        c3.markdown(f"**{len(df_vis)}** enregistrement(s)")


# =====================================================================
# ROUTAGE DES VUES
# =====================================================================
if vue == "BL réception":
    vue_bl(vue, repository.TYPES_ACHAT)
elif vue == "BL expédition":
    vue_bl(vue, repository.TYPES_VENTE)
elif vue == "DESADV achat":
    vue_referentiel("desadv", vue, valeurs_fixes={"sens": repository.SENS_ACHAT},
                    config_colonnes={
                        "numero_bl": st.column_config.TextColumn("Numéro de BL", required=True),
                        "nom_fournisseur": st.column_config.SelectboxColumn(
                            "Fournisseur", options=repository.lister_tiers(repository.TIERS_FOURNISSEUR),
                            required=True),
                    })
elif vue == "DESADV vente":
    vue_referentiel("desadv", vue, valeurs_fixes={"sens": repository.SENS_VENTE},
                    config_colonnes={
                        "numero_bl": st.column_config.TextColumn("Numéro de BL", required=True),
                        "nom_fournisseur": st.column_config.SelectboxColumn(
                            "Client", options=repository.lister_tiers(repository.TIERS_CLIENT),
                            required=True),
                    })
elif vue == "Fournisseurs":
    vue_referentiel("tiers", vue, valeurs_fixes={"type_tiers": repository.TIERS_FOURNISSEUR},
                    config_colonnes={"name": st.column_config.TextColumn("Fournisseur", required=True)})
elif vue == "Clients":
    vue_referentiel("tiers", vue, valeurs_fixes={"type_tiers": repository.TIERS_CLIENT},
                    config_colonnes={"name": st.column_config.TextColumn("Client", required=True)})
elif vue == "Gestionnaires":
    vue_referentiel("gestionnaires", vue,
                    config_colonnes={"code_gestionnaire":
                                     st.column_config.TextColumn("Code gestionnaire", required=True)})
elif vue == "Portefeuilles":
    vue_referentiel("portefeuilles", vue,
                    config_colonnes={
                        "code_gestionnaire": st.column_config.SelectboxColumn(
                            "Gestionnaire", options=repository.lister_gestionnaires(), required=True),
                        "nom_fournisseur": st.column_config.SelectboxColumn(
                            "Fournisseur", options=repository.lister_tiers(repository.TIERS_FOURNISSEUR),
                            required=True),
                    })
elif vue == "Quais":
    vue_referentiel("quais", vue,
                    config_colonnes={"code_quai": st.column_config.TextColumn("Code quai", required=True)})
