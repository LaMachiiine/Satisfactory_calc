"""Test d'intégration de l'app Streamlit via le harnais officiel AppTest.

Exécute le script de bout en bout (chargement Docs.json réel, plan, Sankey,
distribution) et vérifie l'absence d'exception. Sauté si les deps UI ou le
fichier de données manquent.
"""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "src" / "satisfactory_planner" / "ui" / "app.py"
DOCS = Path(__file__).resolve().parents[1] / "data" / "Docs.json"

pytestmark = pytest.mark.skipif(not DOCS.exists(), reason="data/Docs.json absent")


def _radio(at, label):
    return next(r for r in at.radio if r.label == label)


def _selectbox(at, label):
    return next(s for s in at.selectbox if s.label == label)


def _pick_target(at):
    """Sélectionne le premier item cible (aucun par défaut) et relance."""
    box = _selectbox(at, "Item cible")
    box.set_value(box.options[0]).run()
    return at


def test_app_runs_without_exception():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception


def test_app_no_default_target():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    # Aucun item cible par défaut -> pas de plan (pas de métrique puissance).
    assert _selectbox(at, "Item cible").value is None
    assert not any("Puissance" in m.label for m in at.metric)


def test_app_defaults_are_direct_and_max100():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    # Mode par défaut = Direct (forward) ; réalisation par défaut = max 100 % + reste.
    assert _radio(at, "Mode").value.startswith("Direct")
    assert _selectbox(at, "Réalisation machines").value.startswith("Max à 100")


def test_app_inverse_defaults_to_map_deposits():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    _radio(at, "Mode").set_value("Inverse (max output)").run()
    at = _pick_target(at)
    assert not at.exception
    # En inverse + cible choisie : source des bruts par défaut = carte.
    assert _radio(at, "Source des bruts").value.startswith("Gisements")


def test_app_forward_mode_runs():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    _radio(at, "Mode").set_value("Direct (forward)").run()
    at = _pick_target(at)
    assert not at.exception
    assert any("Puissance" in m.label for m in at.metric)


def test_app_alternate_recipe_selection_runs():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    # Le sélecteur d'alternatives est un multiselect ; en choisir une ne doit pas planter.
    ms = next(m for m in at.multiselect if m.label == "Recettes alternatives autorisées")
    if ms.options:
        ms.set_value([ms.options[0]]).run()
    assert not at.exception


def test_app_target_options_stable_across_alternates():
    # Les options « Item cible » ne doivent PAS changer quand on (dé)coche une
    # alternative (catalogue complet) — sinon Streamlit réinitialise la sélection.
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    before = list(_selectbox(at, "Item cible").options)
    ms = next(m for m in at.multiselect if m.label == "Recettes alternatives autorisées")
    if ms.options:
        ms.set_value(list(ms.options)).run()  # active TOUTES les alternatives
    after = list(_selectbox(at, "Item cible").options)
    assert before == after


def test_app_map_add_source_mode_runs():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    r = next((r for r in at.radio if r.label == "Mode carte"), None)
    assert r is not None  # le sélecteur de mode carte existe
    r.set_value("➕ Ajouter une source").run()
    assert not at.exception


def test_app_keeps_target_when_toggling_alternates():
    # L'item cible sélectionné est conservé après avoir (dé)coché des alternatives.
    at = _pick_target(AppTest.from_file(str(APP), default_timeout=60).run())
    target = _selectbox(at, "Item cible").value
    assert target is not None
    ms = next(m for m in at.multiselect if m.label == "Recettes alternatives autorisées")
    if ms.options:
        ms.set_value(list(ms.options)).run()  # active TOUTES les alternatives
    assert _selectbox(at, "Item cible").value == target
