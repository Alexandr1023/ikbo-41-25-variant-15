"""Расчёт порядка загрузки по направлению рёбер графа."""

import heapq

from dependency_graph.errors import DependencyGraphError
from dependency_graph.graph import DependencyGraph


def load_order(graph: DependencyGraph) -> tuple[str, ...]:
    """Возвращает порядок dependencies-first или сообщает о цикле."""
    remaining = {
        node: len(dependencies)
        for node, dependencies in graph.adjacency.items()
    }
    dependents: dict[str, list[str]] = {
        node: [] for node in graph.adjacency
    }
    for node, dependencies in graph.adjacency.items():
        for dependency in dependencies:
            dependents.setdefault(dependency, []).append(node)
    ready = [node for node, count in remaining.items() if count == 0]
    heapq.heapify(ready)
    result = []
    while ready:
        dependency = heapq.heappop(ready)
        result.append(dependency)
        for parent in sorted(dependents.get(dependency, [])):
            remaining[parent] -= 1
            if remaining[parent] == 0:
                heapq.heappush(ready, parent)
    if len(result) != len(remaining):
        cyclic = sorted(node for node, count in remaining.items() if count)
        raise DependencyGraphError(
            "Порядок загрузки невозможен из-за цикла: "
            + ", ".join(cyclic)
        )
    return tuple(result)

