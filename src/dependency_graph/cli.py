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
from dependency_graph.config import (
    ConfigurationError,
    format_config,
    load_config,
)
from dependency_graph.errors import DependencyGraphError


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
    if args.stage is None:
        print("Для запуска укажите реализованный этап через --stage.")
    return 0

