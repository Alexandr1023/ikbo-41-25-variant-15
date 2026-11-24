"""Проверки парсера тестового графа и обхода BFS."""

from pathlib import Path
import unittest

from dependency_graph.errors import DependencyGraphError
from dependency_graph.graph import build_test_graph, parse_test_graph


FIXTURES = Path(__file__).parent / "fixtures"


class GraphTests(unittest.TestCase):
    """Покрывает общие узлы, циклы и ошибочные файлы."""

    def test_bfs_visits_shared_node_once(self) -> None:
        """Не посещает общий транзитивный узел повторно."""
        graph = build_test_graph(FIXTURES / "alpha.graph", "ALPHA")
        self.assertEqual(
            graph.breadth_first_order,
            ("ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO"),
        )
        self.assertEqual(graph.adjacency["CHARLIE"], ("DELTA", "ECHO"))

    def test_bfs_stops_on_cycle(self) -> None:
        """Завершает обход графа с циклической зависимостью."""
        graph = build_test_graph(FIXTURES / "beta.graph", "BETA")
        self.assertEqual(
            graph.breadth_first_order,
            ("BETA", "BRAVO", "CHARLIE", "DELTA", "ECHO"),
        )
        self.assertIn(("CHARLIE", "BRAVO"), graph.edges)

    def test_three_fixtures_have_distinct_roots(self) -> None:
        """Загружает по одному тестовому сценарию на пакет."""
        roots = ("ALPHA", "BETA", "GAMMA")
        for file_name, root in zip(
            ("alpha.graph", "beta.graph", "gamma.graph"), roots
        ):
            with self.subTest(root=root):
                graph = build_test_graph(FIXTURES / file_name, root)
                self.assertEqual(graph.root, root)

    def test_lowercase_name_is_rejected(self) -> None:
        """Отклоняет имя тестового узла в нижнем регистре."""
        with self.assertRaises(DependencyGraphError):
            parse_test_graph(FIXTURES / "invalid.graph")


if __name__ == "__main__":
    unittest.main()
