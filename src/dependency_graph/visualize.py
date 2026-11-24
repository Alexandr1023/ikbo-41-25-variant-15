"""Экспорт графа в текст D2 и изображение SVG."""

from html import escape
import json
from pathlib import Path
import textwrap

from dependency_graph.graph import DependencyGraph

_NODE_WIDTH = 194
_NODE_HEIGHT = 72
_LEVEL_GAP = 86
_ROW_GAP = 40


def _node_levels(graph: DependencyGraph) -> dict[str, int]:
    """Вычисляет уровень каждого узла по BFS-порядку."""
    levels = {graph.root: 0}
    for node in graph.breadth_first_order:
        for dependency in graph.adjacency.get(node, ()):
            if dependency not in levels:
                levels[dependency] = levels[node] + 1
    return levels


def _positions(
    graph: DependencyGraph,
) -> tuple[dict[str, tuple[int, int]], int, int]:
    """Располагает узлы по уровням и строкам."""
    levels = _node_levels(graph)
    groups: dict[int, list[str]] = {}
    for node, level in levels.items():
        groups.setdefault(level, []).append(node)
    positions = {}
    for level, nodes in groups.items():
        for row, node in enumerate(sorted(nodes)):
            x = 42 + level * (_NODE_WIDTH + _LEVEL_GAP)
            y = 54 + row * (_NODE_HEIGHT + _ROW_GAP)
            positions[node] = (x, y)
    max_level = max(groups, default=0)
    max_rows = max((len(nodes) for nodes in groups.values()), default=1)
    width = 84 + max_level * (_NODE_WIDTH + _LEVEL_GAP) + _NODE_WIDTH
    height = 108 + max_rows * (_NODE_HEIGHT + _ROW_GAP)
    return positions, width, height


def _node_id(index: int) -> str:
    """Создаёт безопасный идентификатор узла D2."""
    return f"node_{index}"


def to_d2(graph: DependencyGraph) -> str:
    """Формирует D2-текст с безопасными ID и исходными подписями."""
    identifiers = {
        node: _node_id(index)
        for index, node in enumerate(graph.breadth_first_order)
    }
    lines = ["direction: right", ""]
    for node in graph.breadth_first_order:
        label = json.dumps(node, ensure_ascii=False)
        lines.append(f"{identifiers[node]}: {label}")
    lines.append("")
    for source, target in graph.edges:
        lines.append(f"{identifiers[source]} -> {identifiers[target]}")
    return "\n".join(lines) + "\n"


def _svg_edges(graph: DependencyGraph, positions: dict) -> list[str]:
    """Формирует SVG-линии и кривые со стрелками."""
    lines = []
    for source, target in graph.edges:
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        start_x = x1 + _NODE_WIDTH
        start_y = y1 + _NODE_HEIGHT // 2
        end_x = x2
        end_y = y2 + _NODE_HEIGHT // 2
        if source == target or end_x <= start_x:
            control_y = min(start_y, end_y) - 38
            lines.append(
                f'<path d="M {start_x} {start_y} C {start_x + 50} '
                f'{control_y}, {end_x - 50} {control_y}, {end_x} {end_y}" '
                'fill="none" stroke="#687b91" stroke-width="2" '
                'marker-end="url(#arrow)"/>'
            )
        else:
            lines.append(
                f'<line x1="{start_x}" y1="{start_y}" '
                f'x2="{end_x}" y2="{end_y}" stroke="#687b91" '
                'stroke-width="2" marker-end="url(#arrow)"/>'
            )
    return lines


def _svg_node(node: str, x: int, y: int) -> list[str]:
    """Формирует SVG-группу одного узла."""
    lines = [
        f'<g id="{escape(node, quote=True)}">',
        f'<rect x="{x}" y="{y}" width="{_NODE_WIDTH}" '
        f'height="{_NODE_HEIGHT}" rx="10" fill="#edf4fc" '
        'stroke="#315b83" stroke-width="2"/>',
    ]
    labels = textwrap.wrap(node, width=23) or [node]
    line_height = 16
    first_y = y + _NODE_HEIGHT // 2 - (len(labels) - 1) * line_height // 2
    for index, label in enumerate(labels):
        text_y = first_y + index * line_height + 5
        lines.append(
            f'<text x="{x + _NODE_WIDTH // 2}" y="{text_y}" '
            'text-anchor="middle" font-family="Segoe UI, sans-serif" '
            f'font-size="13" fill="#142a3f">{escape(label)}</text>'
        )
    lines.append("</g>")
    return lines


def to_svg(graph: DependencyGraph) -> str:
    """Рисует рёбра и узлы SVG средствами стандартной библиотеки."""
    positions, width, height = _positions(graph)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        'role="img" aria-labelledby="title">',
        "<title id=\"title\">Граф зависимостей</title>",
        "<defs><marker id=\"arrow\" markerWidth=\"10\" "
        'markerHeight="8" refX="8" refY="4" orient="auto">',
        '<path d="M0,0 L8,4 L0,8 Z" fill="#687b91"/></marker></defs>',
    ]
    lines.extend(_svg_edges(graph, positions))
    for node, (x, y) in positions.items():
        lines.extend(_svg_node(node, x, y))
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def write_visualization(
    graph: DependencyGraph,
    svg_path: Path,
) -> tuple[Path, Path]:
    """Сохраняет SVG и соседний D2-файл в UTF-8."""
    d2_path = svg_path.with_suffix(".d2")
    try:
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(to_svg(graph), encoding="utf-8")
        d2_path.write_text(to_d2(graph), encoding="utf-8")
    except OSError as error:
        raise OSError(f"Не удалось сохранить диаграмму: {error}") from error
    return svg_path, d2_path

