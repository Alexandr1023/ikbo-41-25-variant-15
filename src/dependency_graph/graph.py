"""Построение графа зависимостей алгоритмом BFS."""

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Iterable

from dependency_graph.errors import DependencyGraphError

_PACKAGE_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class DependencyGraph:
    """Достижимая часть графа и порядок обхода в ширину."""

    root: str
    adjacency: dict[str, tuple[str, ...]]
    breadth_first_order: tuple[str, ...]

    @property
    def edges(self) -> tuple[tuple[str, str], ...]:
        """Возвращает все рёбра в порядке узлов и соседей."""
        return tuple(
            (node, dependency)
            for node, dependencies in self.adjacency.items()
            for dependency in dependencies
        )


def _valid_name(value: str, line_number: int) -> str:
    name = value.strip()
    if not _PACKAGE_NAME.fullmatch(name):
        raise DependencyGraphError(
            f"Строка {line_number}: имя пакета должно быть "
            "заглавными латинскими буквами."
        )
    return name


def parse_test_graph(path: Path) -> dict[str, tuple[str, ...]]:
    """Читает файл рёбер формата `ПАКЕТ -> ЗАВИСИМОСТЬ`."""
    adjacency: dict[str, set[str]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise DependencyGraphError(
            f"Не удалось прочитать тестовый граф {path}: {error}"
        ) from error
    for number, raw_line in enumerate(lines, start=1):
        content = raw_line.split("#", maxsplit=1)[0].strip()
        if not content:
            continue
        parts = content.split("->")
        if len(parts) > 2:
            raise DependencyGraphError(
                f"Строка {number}: допускается только один оператор ->."
            )
        source = _valid_name(parts[0], number)
        adjacency.setdefault(source, set())
        if len(parts) == 1 or not parts[1].strip():
            continue
        for item in parts[1].split(","):
            adjacency[source].add(_valid_name(item, number))
    for dependencies in tuple(adjacency.values()):
        for dependency in dependencies:
            adjacency.setdefault(dependency, set())
    return {
        node: tuple(sorted(dependencies))
        for node, dependencies in adjacency.items()
    }


def breadth_first(
    root: str,
    get_dependencies: Callable[[str], Iterable[str]],
) -> DependencyGraph:
    """Обходит граф BFS и игнорирует повторное посещение узлов."""
    pending = deque([root])
    visited = {root}
    order = []
    adjacency: dict[str, tuple[str, ...]] = {}
    while pending:
        node = pending.popleft()
        order.append(node)
        dependencies = tuple(sorted(set(get_dependencies(node))))
        adjacency[node] = dependencies
        for dependency in dependencies:
            if dependency not in visited:
                visited.add(dependency)
                pending.append(dependency)
    return DependencyGraph(root, adjacency, tuple(order))


def build_test_graph(path: Path, root: str) -> DependencyGraph:
    """Строит достижимый граф из тестового файла."""
    source = parse_test_graph(path)
    if root not in source:
        raise DependencyGraphError(
            f"Пакет {root!r} отсутствует в тестовом файле {path}."
        )
    return breadth_first(root, lambda node: source.get(node, ()))

