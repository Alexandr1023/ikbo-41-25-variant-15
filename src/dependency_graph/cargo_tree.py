"""Сравнение графа с выводом штатной команды cargo tree."""

from pathlib import Path
import re
import shutil
import subprocess

from dependency_graph.errors import DependencyGraphError
from dependency_graph.graph import DependencyGraph

_PACKAGE_LINE = re.compile(r"^([A-Za-z0-9_-]+) v([^\s]+)")


def _node_id(line: str) -> str:
    """Выделяет имя и версию пакета из строки Cargo."""
    match = _PACKAGE_LINE.match(line.strip())
    if not match:
        raise DependencyGraphError(
            f"Не удалось разобрать строку cargo tree: {line.strip()}"
        )
    return f"{match.group(1)}@{match.group(2)}"


def parse_cargo_tree(output: str) -> DependencyGraph:
    """Преобразует стандартное дерево Cargo в ориентированный граф."""
    adjacency: dict[str, set[str]] = {}
    stack: list[str] = []
    root = ""
    for line in output.splitlines():
        connector = re.search(r"(?:├──|└──)\s*(.+)$", line)
        if connector is None:
            if not root and line.strip():
                root = _node_id(line)
                stack = [root]
                adjacency.setdefault(root, set())
            continue
        if not root:
            raise DependencyGraphError(
                "В выводе cargo tree нет корневого пакета."
            )
        depth = len(line[:connector.start()]) // 4 + 1
        node = _node_id(connector.group(1))
        stack = stack[:depth]
        if len(stack) != depth:
            raise DependencyGraphError(
                "Не удалось разобрать уровни cargo tree."
            )
        adjacency.setdefault(stack[-1], set()).add(node)
        adjacency.setdefault(node, set())
        stack.append(node)
    if not root:
        raise DependencyGraphError(
            "Команда cargo tree вернула пустой результат."
        )
    ordered = {node: tuple(sorted(edges)) for node, edges in adjacency.items()}
    order = _preorder(root, ordered)
    return DependencyGraph(root, ordered, order)


def _preorder(
    root: str,
    adjacency: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Возвращает порядок узлов в распечатанном дереве."""
    pending = [root]
    seen = set()
    result = []
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        result.append(node)
        pending.extend(reversed(adjacency.get(node, ())))
    return tuple(result)


def cargo_tree_graph(
    manifest_path: Path,
    package_name: str,
) -> DependencyGraph | None:
    """Запускает Cargo только для сравнения уже построенного графа."""
    cargo = shutil.which("cargo")
    if not cargo:
        return None
    command = [
        cargo,
        "tree",
        "--manifest-path",
        str(manifest_path),
        "--package",
        package_name,
        "--edges",
        "normal,build",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=manifest_path.parent,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DependencyGraphError(
            f"Не удалось запустить cargo tree: {error}"
        ) from error
    if result.returncode:
        detail = result.stderr.strip() or "cargo tree завершился с ошибкой"
        raise DependencyGraphError(detail)
    return parse_cargo_tree(result.stdout)


def edge_difference(
    expected: DependencyGraph,
    actual: DependencyGraph,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Возвращает лишние рёбра Cargo и рёбра только нашей модели."""
    expected_edges = set(expected.edges)
    actual_edges = set(actual.edges)
    return actual_edges - expected_edges, expected_edges - actual_edges

