"""CLI minimale (argparse, stdlib).

Phase 0 : commande `build-cache` (Docs.json -> recipes.json normalisé).
Phase 1+ : les commandes `forward` / `max` seront branchées sur le solveur
(elles passeront probablement à `typer`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .. import __version__
from ..data import game_constants
from ..distribution import build_plan_graph, build_step_belt
from ..model.repository import Repository
from ..solver import allocate_somersloops, solve_forward, solve_max_output


def _cmd_build_cache(args: argparse.Namespace) -> int:
    repo = Repository.from_docs(args.docs, enable_alternates=True)
    repo.save_cache(args.out)
    print(
        f"Cache écrit dans {args.out} : "
        f"{len(repo.items)} items, {len(repo.recipes)} recettes, "
        f"{len(repo.machines)} machines (version {repo.game_version})."
    )
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    repo = Repository.from_docs(args.docs, enable_alternates=True)
    alternates = sum(1 for r in repo.recipes.values() if r.is_alternate)
    print(f"Version jeu : {repo.game_version}")
    print(f"Items       : {len(repo.items)}")
    print(f"Recettes    : {len(repo.recipes)} (dont {alternates} alternatives)")
    print(f"Machines    : {len(repo.machines)}")
    return 0


def _add_distribution_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--distribute", action="store_true",
        help="Générer le graphe de distribution pour chaque étape du plan",
    )
    parser.add_argument(
        "--belt", type=int, default=3, choices=range(1, 7), metavar="TIER",
        help="Tier de tapis 1..6 (défaut: 3 = 270/min)",
    )
    parser.add_argument(
        "--layout", default="balanced", choices=["balanced", "linear"],
        help="Disposition du détail tapis : balanced (arbre de fusion) ou linear (cascade)",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=None,
        help="Dossier où écrire les fichiers .dot/.json (sinon résumé texte seul)",
    )


def _emit_distribution(plan, repo: Repository, belt_tier: int, out_dir, layout: str) -> None:
    capacity = game_constants.BELTS[belt_tier - 1].capacity_per_min
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    # Vue globale (chaîne complète, sens de production).
    plan_graph = build_plan_graph(plan, repo)
    print("\n# Chaîne complète (bruts -> produit final)")
    if out_dir:
        (out_dir / "plan.dot").write_text(plan_graph.to_dot(), encoding="utf-8")
        (out_dir / "plan.json").write_text(plan_graph.to_json(), encoding="utf-8")
        print(f"  -> {out_dir / 'plan.dot'}")

    for step in plan.steps:
        item = repo.items.get(step.main_output)
        name = item.name if item else step.main_output
        machine = repo.machines.get(step.recipe.machine)
        mname = machine.name if machine else step.recipe.machine
        graph = build_step_belt(step, repo, plan.item_names, capacity, layout)
        print(
            f"\n# Distribution — {name} via {mname} "
            f"({step.machines}×@{step.clock_label()}, {step.output_rate:g}/min)"
        )
        print(graph.report())
        if out_dir:
            stem = step.recipe.key
            (out_dir / f"{stem}.dot").write_text(graph.to_dot(), encoding="utf-8")
            (out_dir / f"{stem}.json").write_text(graph.to_json(), encoding="utf-8")


def _cmd_forward(args: argparse.Namespace) -> int:
    repo = Repository.from_docs(args.docs, enable_alternates=args.alternates)
    try:
        target_key = repo.resolve_item(args.item)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1
    try:
        plan = solve_forward(
            repo, targets={target_key: args.rate}, objective=args.objective,
            realize_strategy=args.realize,
        )
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.somersloops > 0:
        allocate_somersloops(plan, repo, args.somersloops)
    print(plan.summary())
    if args.distribute:
        _emit_distribution(plan, repo, args.belt, args.out_dir, args.layout)
    return 0


def _parse_available(repo: Repository, spec: str) -> dict[str, float]:
    """`"Iron Ore=480,Water=100"` -> `{Desc_OreIron_C: 480.0, ...}`."""
    out: dict[str, float] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition("=")
        out[repo.resolve_item(name.strip())] = float(value)
    return out


def _cmd_max(args: argparse.Namespace) -> int:
    repo = Repository.from_docs(args.docs, enable_alternates=args.alternates)
    try:
        target_key = repo.resolve_item(args.item)
        available = _parse_available(repo, args.available)
    except (KeyError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    plan = solve_max_output(repo, target_key, available, realize_strategy=args.realize)
    rate = plan.targets[target_key]
    print(f"Sortie max {repo.items[target_key].name} : {rate:.2f} /min\n")
    print(plan.summary())
    if args.distribute:
        _emit_distribution(plan, repo, args.belt, args.out_dir, args.layout)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="planner",
        description="Calculateur & distributeur de production pour Satisfactory.",
    )
    parser.add_argument(
        "--version", action="version", version=f"planner {__version__}"
    )
    sub = parser.add_subparsers(dest="command")

    p_cache = sub.add_parser(
        "build-cache", help="Parse Docs.json -> recipes.json normalisé."
    )
    p_cache.add_argument("docs", type=Path, help="Chemin vers Docs.json")
    p_cache.add_argument(
        "-o", "--out", type=Path, default=Path("data/recipes.json"),
        help="Fichier de cache de sortie (défaut: data/recipes.json)",
    )
    p_cache.set_defaults(func=_cmd_build_cache)

    p_info = sub.add_parser("info", help="Statistiques du Docs.json.")
    p_info.add_argument("docs", type=Path, help="Chemin vers Docs.json")
    p_info.set_defaults(func=_cmd_info)

    p_fwd = sub.add_parser(
        "forward", help="Mode direct : N unités/min d'un item -> plan de production."
    )
    p_fwd.add_argument("item", help="Item cible (clé Desc_..._C ou nom affiché)")
    p_fwd.add_argument("rate", type=float, help="Débit voulu (objets/min)")
    p_fwd.add_argument(
        "--objective", default="min_raw", choices=["min_raw", "min_power", "min_machines"],
        help="Objectif d'optimisation (défaut: min_raw)",
    )
    p_fwd.add_argument(
        "--alternates", action="store_true", help="Activer les recettes alternatives"
    )
    p_fwd.add_argument(
        "--somersloops", type=int, default=0, metavar="N",
        help="Budget de Somersloops à allouer sur les étapes cibles",
    )
    p_fwd.add_argument(
        "--realize", default="uniform", choices=["uniform", "max100", "overclock"],
        help="Réalisation machines/horloge (défaut: uniform = min-puissance)",
    )
    p_fwd.add_argument(
        "--docs", type=Path, default=Path("data/Docs.json"),
        help="Chemin vers Docs.json (défaut: data/Docs.json)",
    )
    _add_distribution_args(p_fwd)
    p_fwd.set_defaults(func=_cmd_forward)

    p_max = sub.add_parser(
        "max", help="Mode inverse : production max d'un item avec les bruts donnés."
    )
    p_max.add_argument("item", help="Item cible (clé Desc_..._C ou nom affiché)")
    p_max.add_argument(
        "--available", required=True,
        help="Bruts disponibles, ex. \"Iron Ore=480,Copper Ore=240\"",
    )
    p_max.add_argument(
        "--alternates", action="store_true", help="Activer les recettes alternatives"
    )
    p_max.add_argument(
        "--realize", default="uniform", choices=["uniform", "max100", "overclock"],
        help="Réalisation machines/horloge (défaut: uniform = min-puissance)",
    )
    p_max.add_argument(
        "--docs", type=Path, default=Path("data/Docs.json"),
        help="Chemin vers Docs.json (défaut: data/Docs.json)",
    )
    _add_distribution_args(p_max)
    p_max.set_defaults(func=_cmd_max)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
