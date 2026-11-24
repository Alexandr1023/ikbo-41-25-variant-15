"""Командная строка приложения."""

import argparse
from pathlib import Path
import sys
import tempfile

from dependency_graph.cargo import (
    clone_repository,
    dependency_lines,
    load_package,
)
from dependency_graph.cargo_graph import build_cargo_graph
from dependency_graph.cargo_tree import cargo_tree_graph, edge_difference
from dependency_graph.config import (
    ConfigurationError,
    format_config,
    load_config,
)
from dependency_graph.errors import DependencyGraphError
from dependency_graph.graph import build_test_graph, parse_test_graph
from dependency_graph.order import load_order


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Построение графа зависимостей Cargo-пакета."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.ini"),
        help="путь к INI-файлу (по умолчанию config.ini)",
    )
    parser.add_argument(
        "--stage",
        type=int,
        choices=range(1, 6),
        help="выполнить один этап задания",
    )
    return parser.parse_args()


def _run_stage_two(config) -> int:
    if config.test_mode:
        try:
            graph = parse_test_graph(Path(config.source))
            if config.package_name not in graph:
                raise DependencyGraphError(
                    f"Пакет {config.package_name!r} не найден в тестовом графе."
                )
            dependencies = graph[config.package_name]
            print(f"Прямые зависимости {config.package_name}:")
            for dependency in dependencies:
                print(f"- {dependency}")
        except DependencyGraphError as error:
            print(f"Ошибка получения данных: {error}", file=sys.stderr)
            return 2
        return 0
    try:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repository"
            clone_repository(config.source, repository)
            package = load_package(repository, config.package_name)
            print(f"Прямые зависимости {package.name}:")
            for line in dependency_lines(package):
                print(f"- {line}")
    except (DependencyGraphError, OSError) as error:
        print(f"Ошибка получения данных: {error}", file=sys.stderr)
        return 2
    return 0


def _print_graph(graph) -> None:
    print(f"Корневой пакет: {graph.root}")
    print("Порядок BFS: " + " -> ".join(graph.breadth_first_order))
    print("Рёбра графа:")
    for node, dependency in graph.edges:
        print(f"- {node} -> {dependency}")


def _load_graph(config, temporary_root: Path):
    if config.test_mode:
        return build_test_graph(Path(config.source), config.package_name), None
    repository = temporary_root / "repository"
    clone_repository(config.source, repository)
    package = load_package(repository, config.package_name)
    graph = build_cargo_graph(repository, package, temporary_root)
    return graph, package


def _run_stage_three(config) -> int:
    try:
        with tempfile.TemporaryDirectory() as temporary:
            graph, _ = _load_graph(config, Path(temporary))
    except (DependencyGraphError, OSError) as error:
        print(f"Ошибка построения графа: {error}", file=sys.stderr)
        return 2
    _print_graph(graph)
    return 0


def _run_stage_four(config) -> int:
    try:
        with tempfile.TemporaryDirectory() as temporary:
            graph, package = _load_graph(config, Path(temporary))
            _print_graph(graph)
            try:
                order = load_order(graph)
                print("Порядок загрузки: " + " -> ".join(order))
            except DependencyGraphError as error:
                print(str(error))
            if config.test_mode:
                print("Сравнение с cargo tree пропущено: тестовый граф.")
                return 0
            if package is None:
                return 0
            comparison = cargo_tree_graph(
                package.manifest_path,
                package.name,
            )
            if comparison is None:
                print("Сравнение не выполнено: cargo не установлен.")
                return 0
            _print_cargo_comparison(graph, comparison)
    except (DependencyGraphError, OSError) as error:
        print(f"Ошибка сравнения: {error}", file=sys.stderr)
        return 2
    return 0


def _print_cargo_comparison(graph, comparison) -> None:
    missing, extra = edge_difference(graph, comparison)
    try:
        cargo_order = load_order(comparison)
    except DependencyGraphError as error:
        print(f"Порядок cargo tree не вычислен: {error}")
    else:
        print("Порядок cargo tree: " + " -> ".join(cargo_order))
    if not missing and not extra:
        print("Граф совпадает с cargo tree.")
        return
    print(f"Рёбер только в cargo tree: {len(missing)}")
    print(f"Рёбер только в BFS-графе: {len(extra)}")
    print(
        "Возможные причины: версии без Cargo.lock, активные features "
        "или целевые платформы."
    )


def main() -> int:
    """Запускает выбранный этап приложения."""
    args = _arguments()
    try:
        config = load_config(args.config)
    except ConfigurationError as error:
        print(f"Ошибка конфигурации: {error}", file=sys.stderr)
        return 2
    if args.stage == 1:
        print(format_config(config))
        return 0
    if args.stage == 2:
        return _run_stage_two(config)
    if args.stage == 3:
        return _run_stage_three(config)
    if args.stage == 4:
        return _run_stage_four(config)
    if args.stage is None:
        return _run_stage_three(config)
    print("Выбранный этап ещё не реализован.")
    return 0

