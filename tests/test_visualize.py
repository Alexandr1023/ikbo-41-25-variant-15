"""Проверки экспорта графа в D2 и SVG."""

from pathlib import Path
import tempfile
import unittest

from dependency_graph.graph import build_test_graph
from dependency_graph.visualize import to_d2, to_svg, write_visualization


FIXTURES = Path(__file__).parent / "fixtures"


class VisualizationTests(unittest.TestCase):
    """Проверяет содержимое и запись двух форматов диаграммы."""

    def setUp(self) -> None:
        """Подготавливает тестовую диаграмму."""
        self.graph = build_test_graph(FIXTURES / "gamma.graph", "GAMMA")

    def test_d2_contains_nodes_and_edges(self) -> None:
        """Проверяет D2-подписи и рёбра."""
        diagram = to_d2(self.graph)
        self.assertIn("direction: right", diagram)
        self.assertIn('node_0: "GAMMA"', diagram)
        self.assertIn("node_0 -> node_1", diagram)

    def test_svg_contains_accessible_graph_and_edges(self) -> None:
        """Проверяет SVG-заголовок, узлы и стрелки."""
        svg = to_svg(self.graph)
        self.assertIn("<svg ", svg)
        self.assertIn("Граф зависимостей", svg)
        self.assertIn('marker-end="url(#arrow)"', svg)
        self.assertIn("KAPPA", svg)

    def test_both_files_are_written(self) -> None:
        """Сохраняет SVG и соседний исходник D2."""
        with tempfile.TemporaryDirectory() as temporary:
            svg_path = Path(temporary) / "graph.svg"
            created_svg, created_d2 = write_visualization(
                self.graph,
                svg_path,
            )
            self.assertTrue(created_svg.is_file())
            self.assertTrue(created_d2.is_file())


if __name__ == "__main__":
    unittest.main()
