"""Onglet carte des gisements (§5bis.5), style satisfactory-calculator.

Fond de carte du jeu (image communautaire) en ImageOverlay + marqueurs cliquables
colorés par pureté, opacité réduite si occupé. Clic = bascule disponible/occupé
(persisté). Projection : coordonnées monde `[y, x]` (convention LancelotP/SCIM),
CRS.Simple. Noms de ressources lisibles et filtre d'affichage par ressource.
"""

from __future__ import annotations

import base64
import functools
from pathlib import Path

from ..nodes.extraction import node_extraction_rate
from ..nodes.state import NodeState, save_states

DEFAULT_STATE_PATH = "nodes_state.json"
MAP_BACKGROUND_PATH = "data/map_background.jpg"
ICON_DIR = "data/icons"  # icônes de ressource (one PNG per item_key)

# Échelle monde -> plan carte (LancelotP : 1/6400). Ramène les ±500 000 UE dans une
# plage gérable par CRS.Simple (sinon le zoom est clampé et rien n'est visible).
_SCALE = 6400.0
# Bornes jouables du jeu (cm). SCIM tuile une zone ÉLARGIE de extraBackgroundSize /
# backgroundSize = 4096/32768 = 1/8 de chaque côté (marge océan/noir) ; le fond
# assemblé (scripts/fetch_map_background.py) couvre donc ces bornes élargies.
_PLAY_WEST, _PLAY_EAST = -324698.832031, 425301.832031  # x : ouest -> est
_PLAY_NORTH, _PLAY_SOUTH = -375000.0, 375000.0          # y : nord -> sud (+Y = sud)
_PAD = 1.0 / 8.0
_OX = (_PLAY_EAST - _PLAY_WEST) * _PAD
_OY = (_PLAY_SOUTH - _PLAY_NORTH) * _PAD
WORLD_WEST, WORLD_EAST = _PLAY_WEST - _OX, _PLAY_EAST + _OX
WORLD_NORTH, WORLD_SOUTH = _PLAY_NORTH - _OY, _PLAY_SOUTH + _OY
# CRS.Simple folium : +lat vers le HAUT, or en jeu +Y vers le SUD -> lat = -y/échelle
# (nord en haut), lng = x/échelle.
MAP_BOUNDS = [
    [-WORLD_SOUTH / _SCALE, WORLD_WEST / _SCALE],  # [lat_min (sud), lng_min (ouest)]
    [-WORLD_NORTH / _SCALE, WORLD_EAST / _SCALE],  # [lat_max (nord), lng_max (est)]
]

PURITY_COLOR = {"impure": "#d9534f", "normal": "#f0ad4e", "pure": "#5cb85c"}
GEYSER_COLOR = "#9b59b6"  # geyser : énergie géothermique (hors puretés)


def world_to_latlng(x: float, y: float) -> tuple[float, float]:
    """Projette une coordonnée monde (x, y) en (lat, lng) pour folium CRS.Simple.

    `lat = -y/échelle` pour garder le nord en haut (en jeu +Y = sud), `lng = x/échelle`.
    """
    return (-y / _SCALE, x / _SCALE)


def latlng_to_world(lat: float, lng: float) -> tuple[float, float]:
    """Inverse de `world_to_latlng` : (lat, lng) folium -> (x, y) monde (cm)."""
    return (lng * _SCALE, -lat * _SCALE)


def marker_color(node) -> str:
    """Couleur du marqueur : par pureté (node/well), dédiée pour un geyser."""
    if node.kind == "geyser":
        return GEYSER_COLOR
    return PURITY_COLOR.get(node.purity, "#777")


@functools.lru_cache(maxsize=1)
def _background_data_uri() -> str | None:
    """Image de fond encodée en data URI (None si absente)."""
    p = Path(MAP_BACKGROUND_PATH)
    if not p.exists():
        return None
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


@functools.lru_cache(maxsize=64)
def icon_data_uri(resource: str, icon_dir: str | Path = ICON_DIR) -> str | None:
    """Icône de la ressource (PNG `<icon_dir>/<resource>.png`) en data URI, ou None."""
    p = Path(icon_dir) / f"{resource}.png"
    if not p.exists():
        return None
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _icon_style(resources) -> str:
    """Bloc <style> définissant l'image de chaque icône UNE seule fois (classe CSS).

    Évite de réinjecter le base64 dans les 600 marqueurs (HTML qui explosait à ~50 Mo).
    """
    rules = []
    for res in sorted(resources):
        uri = icon_data_uri(res)
        if uri:
            rules.append(
                f".sfm-{res}{{background:#fff center/70% no-repeat url('{uri}') !important;}}"
            )
    return "<style>" + "".join(rules) + "</style>"


def _marker_icon(node, opacity: float, ring: str):
    """Pastille ronde (anneau = pureté) portant l'icône de ressource ; repli plein."""
    import folium

    size = 26 if node.kind == "geyser" else 22
    has_icon = icon_data_uri(node.resource) is not None
    cls = f"sfm-{node.resource}" if has_icon else ""
    bg = "" if has_icon else f"background:{ring};"
    html = (
        f'<div class="{cls}" style="width:{size}px;height:{size}px;border-radius:50%;'
        f'border:3px solid {ring};{bg}box-sizing:border-box;'
        f'box-shadow:0 0 3px rgba(0,0,0,.7);opacity:{opacity};"></div>'
    )
    return folium.DivIcon(html=html, icon_size=(size, size), icon_anchor=(size // 2, size // 2))


def node_tooltip(node, state: NodeState, name: str | None = None) -> str:
    statut = "disponible" if state.available else "occupé"
    if node.kind == "geyser":
        return f"Geyser — {statut}\nÉnergie géothermique (générateur)"
    rate = node_extraction_rate(node, state)
    label = name or node.resource
    if node.kind == "well":
        # Puits : extracteurs uniformes, seul l'overclock du pressuriseur joue.
        return (
            f"{label} ({node.purity}) — puits — {statut}\n"
            f"@ {state.clock:.0f}% → {rate:g}/min"
        )
    return (
        f"{label} ({node.purity}) — {statut}\n"
        f"Mk.{state.miner_tier} @ {state.clock:.0f}% → {rate:g}/min"
    )


def _base_map():
    """Carte folium vide : fond du jeu (ImageOverlay) + cadrage sur MAP_BOUNDS."""
    import folium

    center = [(MAP_BOUNDS[0][0] + MAP_BOUNDS[1][0]) / 2, (MAP_BOUNDS[0][1] + MAP_BOUNDS[1][1]) / 2]
    fmap = folium.Map(location=center, zoom_start=2, crs="Simple", tiles=None)
    uri = _background_data_uri()
    if uri:
        folium.raster_layers.ImageOverlay(image=uri, bounds=MAP_BOUNDS, opacity=0.85).add_to(fmap)
    fmap.fit_bounds(MAP_BOUNDS)
    return fmap


def build_folium_map(
    nodes, states: dict[str, NodeState],
    names: dict[str, str] | None = None,
    visible: set[str] | None = None,
    custom_sources=None,
):
    """Construit la carte folium : fond + marqueurs (filtrés par ressource).

    `custom_sources` (optionnel) : sources perso 🏭 ajoutées par-dessus les gisements.
    """
    import folium

    fmap = _base_map()
    shown = [n for n in nodes if visible is None or n.resource in visible]
    # Icônes définies une seule fois (classes CSS) -> HTML léger.
    fmap.get_root().header.add_child(
        folium.Element(_icon_style({n.resource for n in shown}))
    )

    names = names or {}
    for node in shown:
        state = states.get(node.id) or NodeState()
        lat, lng = world_to_latlng(node.x, node.y)
        opacity = 0.95 if state.available else 0.3
        folium.Marker(
            location=[lat, lng],
            icon=_marker_icon(node, opacity, marker_color(node)),
            tooltip=node_tooltip(node, state, names.get(node.resource)),
        ).add_to(fmap)

    for cs in (custom_sources or []):
        clat, clng = world_to_latlng(cs.x, cs.y)
        nm = names.get(cs.item, cs.item)
        folium.Marker(
            location=[clat, clng],
            icon=folium.DivIcon(
                html='<div style="font-size:20px;line-height:20px;'
                'transform:translate(-50%,-50%)">🏭</div>',
                icon_size=(20, 20), icon_anchor=(0, 0),
            ),
            tooltip=f"{nm} — {cs.rate_per_min:g}/min (source perso)",
        ).add_to(fmap)
    return fmap


def build_siting_map(result, names: dict[str, str] | None = None,
                     link_colors: dict[str, str] | None = None):
    """Carte d'une localisation d'usine : pin usine, gisements retenus, lignes (§5ter.6).

    `link_colors` : couleur de chaque liaison par id de source (mode de transport).
    """
    import folium

    names = names or {}
    link_colors = link_colors or {}
    fmap = _base_map()
    slat, slng = world_to_latlng(*result.site)
    for pick in result.picks:
        s = pick.source
        lat, lng = world_to_latlng(s.x, s.y)
        folium.PolyLine(
            [(slat, slng), (lat, lng)], color=link_colors.get(s.id, "#444"),
            weight=3, opacity=0.7,
        ).add_to(fmap)
        nm = names.get(s.item, s.item)
        folium.CircleMarker(
            location=[lat, lng], radius=6, color="#2a7", fill=True, fill_opacity=0.9,
            weight=2, tooltip=f"{nm} — {pick.flow:g}/min @ {pick.dist_m:.0f} m",
        ).add_to(fmap)
    folium.Marker(
        location=[slat, slng],
        icon=folium.DivIcon(
            html='<div style="font-size:26px;line-height:26px;'
            'transform:translate(-50%,-100%)">📍</div>',
            icon_size=(26, 26), icon_anchor=(0, 0),
        ),
        tooltip="Usine",
    ).add_to(fmap)
    return fmap


def render_siting(result, names: dict[str, str] | None = None,
                  link_colors: dict[str, str] | None = None) -> None:
    """Affiche la carte d'une localisation d'usine dans Streamlit (lecture seule)."""
    import streamlit as st
    from streamlit_folium import st_folium

    st.caption("📍 = usine ; cercles = gisements retenus ; lignes colorées = mode de transport.")
    st_folium(
        build_siting_map(result, names, link_colors), height=600,
        use_container_width=True, returned_objects=[],
    )


def _nearest_node_id(nodes, lat: float, lng: float, visible: set[str] | None = None):
    """Gisement (visible) dont la position est la plus proche du clic."""
    best, best_d = None, float("inf")
    for node in nodes:
        if visible is not None and node.resource not in visible:
            continue
        nlat, nlng = world_to_latlng(node.x, node.y)
        d = (nlat - lat) ** 2 + (nlng - lng) ** 2
        if d < best_d:
            best, best_d = node.id, d
    return best


def render(
    nodes, states: dict[str, NodeState],
    names: dict[str, str] | None = None,
    visible: set[str] | None = None,
    state_path: str = DEFAULT_STATE_PATH,
    custom_sources=None,
) -> None:
    """Onglet Streamlit : carte + bascule de disponibilité au clic (persistée)."""
    import streamlit as st
    from streamlit_folium import st_folium

    st.caption(
        "Clique un gisement pour basculer disponible/occupé. Vert = pur, "
        "orange = normal, rouge = impur ; opacité réduite = occupé."
    )
    result = st_folium(
        build_folium_map(nodes, states, names, visible, custom_sources), height=600,
        use_container_width=True, returned_objects=["last_object_clicked"],
    )
    clicked = (result or {}).get("last_object_clicked")
    if clicked:
        key = (round(clicked["lat"], 2), round(clicked["lng"], 2))
        if st.session_state.get("_last_node_click") != key:
            st.session_state["_last_node_click"] = key
            node_id = _nearest_node_id(nodes, clicked["lat"], clicked["lng"], visible)
            if node_id:
                state = states.get(node_id) or NodeState()
                state.available = not state.available
                states[node_id] = state
                save_states(states, state_path)
                st.rerun()


def render_placement(
    nodes, states: dict[str, NodeState],
    names: dict[str, str] | None = None,
    visible: set[str] | None = None,
    custom_sources=None,
) -> tuple[float, float] | None:
    """Carte en mode placement : renvoie (x, y) monde du dernier clic NEUF, sinon None."""
    import streamlit as st
    from streamlit_folium import st_folium

    st.caption("Clique sur la carte pour positionner la source à ajouter.")
    result = st_folium(
        build_folium_map(nodes, states, names, visible, custom_sources),
        height=600, use_container_width=True, returned_objects=["last_clicked"],
    )
    clicked = (result or {}).get("last_clicked")
    if not clicked:
        return None
    key = (round(clicked["lat"], 4), round(clicked["lng"], 4))
    if st.session_state.get("_last_place_click") == key:
        return None
    st.session_state["_last_place_click"] = key
    return latlng_to_world(clicked["lat"], clicked["lng"])
