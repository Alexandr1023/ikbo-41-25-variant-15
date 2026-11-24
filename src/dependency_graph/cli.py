"""Командная строка приложения."""

import argparse
from pathlib import Path
import sys

from dependency_graph.config import (
    ConfigurationError,
    format_config,
    load_config,
)


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
    if args.stage in (None, 1):
        print(format_config(config))
        if args.stage == 1:
            return 0
    print("Этапы 2–5 будут добавлены в следующих версиях.")
    return 0

