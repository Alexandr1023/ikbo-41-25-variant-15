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
from dependency_graph.visualize import write_visualization

STAGE_CONFIG = 1
STAGE_DIRECT = 2
STAGE_GRAPH = 3
STAGE_ORDER = 4
STAGE_VISUALIZE = 5


def _arguments() -> argparse.Namespace:
    """Разбирает аргументы командной строки."""
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
        choices=range(STAGE_CONFIG, STAGE_VISUALIZE + 1),
        help="выполнить один этап задания",
    )
    return parser.parse_args()


def _run_stage_two(config) -> int:
    """Показывает прямые зависимости Cargo-пакета."""
    if config.test_mode:
        try:
            graph = parse_test_graph(Path(config.source))
            if config.package_name not in graph:
                raise DependencyGraphError(
                    f"Пакет {config.package_name!r} не найден в тестовом графе."
                )
            dependencies = graph[config.package_name]
            print(f"Прямые зависимости {config.package_name}:")
            if dependencies:
                for dependency in dependencies:
                    print(f"- {dependency}")
            else:
                print("- Прямых зависимостей нет.")
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
    """Печатает порядок BFS и рёбра графа."""
    print(f"Корневой пакет: {graph.root}")
    print("Порядок BFS: " + " -> ".join(graph.breadth_first_order))
    print("Рёбра графа:")
    for node, dependency in graph.edges:
        print(f"- {node} -> {dependency}")


def _load_graph(config, temporary_root: Path):
    """Создаёт тестовый или Cargo-граф по конфигурации."""
    if config.test_mode:
        return build_test_graph(Path(config.source), config.package_name), None
    repository = temporary_root / "repository"
    clone_repository(config.source, repository)
    package = load_package(repository, config.package_name)
    graph = build_cargo_graph(repository, package, temporary_root)
    return graph, package


def _run_stage_three(config) -> int:
    """Запускает построение и печать транзитивного графа."""
    try:
        with tempfile.TemporaryDirectory() as temporary:
            graph, _ = _load_graph(config, Path(temporary))
    except (DependencyGraphError, OSError) as error:
        print(f"Ошибка построения графа: {error}", file=sys.stderr)
        return 2
    _print_graph(graph)
    return 0


def _run_stage_four(config) -> int:
    """Печатает порядок загрузки и сравнивает Cargo-граф."""
    try:
        with tempfile.TemporaryDirectory() as temporary:
            graph, package = _load_graph(config, Path(temporary))
            _print_graph(graph)
            try:
                order = load_order(graph)
                print("Порядок загрузки: " + " -> ".join(order))
            except DependencyGraphError as error:
                print(str(error))
            _compare_graph(config, graph, package)
    except (DependencyGraphError, OSError) as error:
        print(f"Ошибка сравнения: {error}", file=sys.stderr)
        return 2
    return 0


def _compare_graph(config, graph, package) -> None:
    """Сравнивает граф с cargo tree, если данные доступны."""
    if config.test_mode:
        print("Сравнение с cargo tree пропущено: тестовый граф.")
        return
    if package is None:
        return
    comparison = cargo_tree_graph(package.manifest_path, package.name)
    if comparison is None:
        print("Сравнение не выполнено: cargo не установлен.")
        return
    _print_cargo_comparison(graph, comparison)


def _print_cargo_comparison(graph, comparison) -> None:
    """Печатает порядок и различия между двумя графами."""
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


def _run_stage_five(config) -> int:
    """Создаёт D2-диаграмму и SVG-файл."""
    try:
        with tempfile.TemporaryDirectory() as temporary:
            graph, package = _load_graph(config, Path(temporary))
            svg_path, d2_path = write_visualization(
                graph,
                config.output_file,
            )
            print(f"D2-диаграмма сохранена: {d2_path}")
            print(f"Изображение SVG сохранено: {svg_path}")
            _compare_graph(config, graph, package)
    except (DependencyGraphError, OSError) as error:
        print(f"Ошибка визуализации: {error}", file=sys.stderr)
        return 2
    return 0


def _run_all(config) -> int:
    """Выполняет все этапы в одной загрузке репозитория."""
    try:
        with tempfile.TemporaryDirectory() as temporary:
            graph, package = _load_graph(config, Path(temporary))
            _print_pipeline(config, graph, package)
    except (DependencyGraphError, OSError) as error:
        print(f"Ошибка выполнения: {error}", file=sys.stderr)
        return 2
    return 0


def _print_pipeline(config, graph, package) -> None:
    """Показывает результаты пяти этапов анализа."""
    print(format_config(config))
    dependencies = (
        graph.adjacency.get(graph.root, ())
        if package is None
        else dependency_lines(package)
    )
    print("\nЭтап 2. Прямые зависимости:")
    if dependencies:
        for dependency in dependencies:
            print(f"- {dependency}")
    else:
        print("- Прямых зависимостей нет.")
    print("\nЭтап 3. Граф BFS:")
    _print_graph(graph)
    print("\nЭтап 4. Порядок загрузки:")
    try:
        print(" -> ".join(load_order(graph)))
    except DependencyGraphError as error:
        print(str(error))
    _compare_graph(config, graph, package)
    svg_path, d2_path = write_visualization(graph, config.output_file)
    print(f"\nD2-диаграмма сохранена: {d2_path}")
    print(f"Изображение SVG сохранено: {svg_path}")


def main() -> int:
    """Запускает выбранный этап приложения."""
    args = _arguments()
    try:
        config = load_config(args.config)
    except ConfigurationError as error:
        print(f"Ошибка конфигурации: {error}", file=sys.stderr)
        return 2
    if args.stage == STAGE_CONFIG:
        print(format_config(config))
        return 0
    if args.stage == STAGE_DIRECT:
        return _run_stage_two(config)
    if args.stage == STAGE_GRAPH:
        return _run_stage_three(config)
    if args.stage == STAGE_ORDER:
        return _run_stage_four(config)
    if args.stage == STAGE_VISUALIZE:
        return _run_stage_five(config)
    if args.stage is None:
        return _run_all(config)
    print("Выбранный этап ещё не реализован.")
    return 0

