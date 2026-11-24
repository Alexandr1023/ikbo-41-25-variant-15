"""Проверки порядка загрузки и чтения дерева Cargo."""

from pathlib import Path
import unittest

from dependency_graph.cargo_tree import parse_cargo_tree
from dependency_graph.errors import DependencyGraphError
from dependency_graph.graph import build_test_graph
from dependency_graph.order import load_order


FIXTURES = Path(__file__).parent / "fixtures"


class OrderTests(unittest.TestCase):
    """Проверяет порядок зависимостей и обработку циклов."""

    def test_dependencies_load_before_the_root(self) -> None:
        graph = build_test_graph(FIXTURES / "alpha.graph", "ALPHA")
        self.assertEqual(
            load_order(graph),
            ("DELTA", "BRAVO", "ECHO", "CHARLIE", "ALPHA"),
        )

    def test_cycle_has_no_loading_order(self) -> None:
        graph = build_test_graph(FIXTURES / "beta.graph", "BETA")
        with self.assertRaises(DependencyGraphError):
            load_order(graph)

    def test_cargo_tree_is_converted_to_edges(self) -> None:
        output = (
            "root v1.0.0\n"
            "├── alpha v1.0.0\n"
            "│   └── shared v2.0.0\n"
            "└── beta v1.0.0\n"
            "    └── shared v2.0.0 (*)\n"
        )
        graph = parse_cargo_tree(output)
        self.assertEqual(
            set(graph.edges),
            {
                ("root@1.0.0", "alpha@1.0.0"),
                ("root@1.0.0", "beta@1.0.0"),
                ("alpha@1.0.0", "shared@2.0.0"),
                ("beta@1.0.0", "shared@2.0.0"),
            },
        )


if __name__ == "__main__":
    unittest.main()
