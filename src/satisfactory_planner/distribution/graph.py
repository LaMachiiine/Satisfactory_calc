"""Graphe de distribution + exports DOT/JSON/texte (§5.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..data.game_constants import belt_for_rate

NODE_KINDS = (
    "source", "custom_source", "splitter_2", "splitter_3",
    "merger_2", "merger_3", "machine", "product",
)


@dataclass
class Node:
    id: str
    kind: str
    label: str = ""


@dataclass
class Edge:
    src: str
    dst: str
    rate: float
    label: str = ""  # libellé optionnel (ex. nom de l'item transporté)
    recycled: bool = False  # sous-produit réinjecté (recyclage) -> style distinct


@dataclass
class DistributionGraph:
    """Nœuds typés (source/splitter/merger/machine) et arêtes portant un débit."""

    item_key: str = ""
    belt_capacity: float = 0.0
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    _counter: int = 0

    def add_node(self, kind: str, label: str = "") -> str:
        self._counter += 1
        node_id = f"{kind}_{self._counter}"
        self.nodes.append(Node(node_id, kind, label))
        return node_id

    def add_edge(self, src: str, dst: str, rate: float, label: str = "",
                 recycled: bool = False) -> None:
        self.edges.append(Edge(src, dst, round(rate, 6), label, recycled))

    def count(self, kind: str) -> int:
        return sum(1 for n in self.nodes if n.kind == kind)

    def leaf_rate_total(self) -> float:
        """Somme des débits arrivant aux machines (feuilles)."""
        machine_ids = {n.id for n in self.nodes if n.kind == "machine"}
        return round(sum(e.rate for e in self.edges if e.dst in machine_ids), 6)

    def over_capacity_edges(self) -> list[Edge]:
        """Arêtes dont le débit dépasse la capacité du tapis retenu."""
        if self.belt_capacity <= 0:
            return []
        return [e for e in self.edges if e.rate > self.belt_capacity + 1e-9]

    @staticmethod
    def _tier_for(rate: float) -> int | None:
        belt = belt_for_rate(rate)
        return belt.tier if belt else None

    def _edge_label(self, e: Edge) -> str:
        tier = self._tier_for(e.rate)
        tier_txt = f"Mk.{tier}" if tier else ">Mk.6"
        prefix = f"{e.label} " if e.label else ""
        return f"{prefix}{e.rate:g}/min · {tier_txt}"

    _STYLE = {
        "source": ('shape=box, style="filled,rounded", fillcolor="#bcdcff"', None),
        # Source personnalisée (sortie d'usine) : carré bleu plein, distinct du brut.
        "custom_source": (
            'shape=box, style=filled, fillcolor="#5b9bd5", fontcolor="white"', None
        ),
        "splitter_2": ("shape=diamond, style=filled, fillcolor=\"#f5e08c\"", "÷2"),
        "splitter_3": ("shape=diamond, style=filled, fillcolor=\"#f5e08c\"", "÷3"),
        "merger_2": ("shape=invtriangle, style=filled, fillcolor=\"#f0c674\"", "⊕2"),
        "merger_3": ("shape=invtriangle, style=filled, fillcolor=\"#f0c674\"", "⊕3"),
        "machine": ('shape=box, style="filled,rounded", fillcolor="#bff0bf"', None),
        "product": ('shape=box, style="filled,rounded", fillcolor="#ffd9a8"', None),
    }

    def to_dot(self) -> str:
        lines = [
            f'digraph "{self.item_key}" {{',
            "  rankdir=LR;",
            '  node [fontname="Helvetica", fontsize=10];',
            '  edge [fontname="Helvetica", fontsize=9];',
        ]
        for n in self.nodes:
            attrs, default_label = self._STYLE.get(n.kind, ("shape=ellipse", None))
            label = n.label or default_label or n.kind
            lines.append(f'  "{n.id}" [label="{label}", {attrs}];')
        # Regroupe par paire de nœuds : un flux dans LES DEUX sens (recyclage) devient
        # une seule arête bidirectionnelle (double flèche, débit dans chaque sens).
        pairs: dict[tuple[str, str], dict[str, list[Edge]]] = {}
        for e in self.edges:
            a, b = (e.src, e.dst) if e.src <= e.dst else (e.dst, e.src)
            slot = pairs.setdefault((a, b), {"ab": [], "ba": []})
            slot["ab" if e.src == a else "ba"].append(e)
        for (a, b), slot in pairs.items():
            ab, ba = slot["ab"], slot["ba"]
            if ab and ba:  # bidirectionnel : double flèche
                fwd = "\\n".join("▶ " + self._edge_label(e) for e in ab)
                bwd = "\\n".join("◀ " + self._edge_label(e) for e in ba)
                lines.append(
                    f'  "{a}" -> "{b}" [dir=both, label="{fwd}\\n{bwd}", '
                    'color="#0aacc0", fontcolor="#0a7", style=dashed];'
                )
                continue
            for e in ab or ba:
                over = self.belt_capacity > 0 and e.rate > self.belt_capacity + 1e-9
                if over:
                    attrs = ', color="#d33", penwidth=2, fontcolor="#d33"'
                elif e.recycled:
                    attrs = ', color="#0aacc0", fontcolor="#0a7", style=dashed'
                else:
                    attrs = ""
                label = ("♻ " if e.recycled else "") + self._edge_label(e)
                lines.append(f'  "{e.src}" -> "{e.dst}" [label="{label}"{attrs}];')
        lines.append("}")
        return "\n".join(lines)

    def to_json(self) -> str:
        data = {
            "item_key": self.item_key,
            "belt_capacity": self.belt_capacity,
            "nodes": [{"id": n.id, "kind": n.kind, "label": n.label} for n in self.nodes],
            "edges": [
                {
                    "src": e.src, "dst": e.dst, "rate": e.rate,
                    "recycled": e.recycled,
                    "tier": self._tier_for(e.rate),
                    "over_capacity": e.rate > self.belt_capacity + 1e-9
                    if self.belt_capacity > 0 else False,
                }
                for e in self.edges
            ],
            "notes": self.notes,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def report(self) -> str:
        lines = [f"Distribution de {self.item_key or '?'} :"]
        lines.append(
            f"  répartiteurs : {self.count('splitter_2')} (1->2), "
            f"{self.count('splitter_3')} (1->3)"
        )
        mergers = self.count("merger_2") + self.count("merger_3")
        if mergers:
            lines.append(f"  groupeurs : {mergers}")
        lines.append(f"  machines : {self.count('machine')}")
        if self.edges:
            max_edge = max(e.rate for e in self.edges)
            tier = self._tier_for(max_edge)
            tier_txt = f"Mk.{tier}" if tier else ">Mk.6"
            lines.append(f"  charge max d'arête : {max_edge:g}/min (tapis {tier_txt})")
        over = self.over_capacity_edges()
        if over:
            lines.append(
                f"  ALERTE : {len(over)} arête(s) > capacité ({self.belt_capacity:g}/min)"
            )
        for note in self.notes:
            lines.append(f"  note : {note}")
        return "\n".join(lines)
