"""Проверки параметров и сообщений конфигурации."""

from pathlib import Path
import tempfile
import unittest

from dependency_graph.config import (
    ConfigurationError,
    format_config,
    load_config,
)


class ConfigTests(unittest.TestCase):
    """Покрывает ошибки каждого поля INI."""

    def setUp(self) -> None:
        """Создаёт временный тестовый граф и путь INI."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.graph = self.root / "graph.txt"
        self.graph.write_text("ALPHA\n", encoding="utf-8")
        self.config_path = self.root / "config.ini"

    def _load(self, values: dict[str, str]):
        """Записывает параметры и читает временную конфигурацию."""
        lines = ["[application]"]
        lines.extend(f"{key} = {value}" for key, value in values.items())
        self.config_path.write_text("\n".join(lines), encoding="utf-8")
        return load_config(self.config_path)

    def _valid_values(self) -> dict[str, str]:
        """Возвращает корректный набор параметров."""
        return {
            "package_name": "ALPHA",
            "source": str(self.graph),
            "test_mode": "true",
            "output_file": "graph.svg",
        }

    def test_valid_config_prints_all_parameters(self) -> None:
        """Проверяет вывод четырёх параметров ключ-значение."""
        config = self._load(self._valid_values())
        output = format_config(config)
        self.assertIn("имя_пакета=ALPHA", output)
        self.assertIn("тестовый_режим=true", output)

    def test_package_name_error(self) -> None:
        """Отклоняет недопустимые символы в имени пакета."""
        values = self._valid_values()
        values["package_name"] = "bad/name"
        with self.assertRaises(ConfigurationError):
            self._load(values)

    def test_source_error(self) -> None:
        """Отклоняет отсутствующий тестовый файл и неверный URL."""
        values = self._valid_values()
        values["source"] = str(self.root / "missing.graph")
        with self.assertRaises(ConfigurationError):
            self._load(values)
        values.update(test_mode="false", source="not-a-url")
        with self.assertRaises(ConfigurationError):
            self._load(values)

    def test_test_mode_error(self) -> None:
        """Принимает только true или false в test_mode."""
        values = self._valid_values()
        values["test_mode"] = "yes"
        with self.assertRaises(ConfigurationError):
            self._load(values)

    def test_output_file_error(self) -> None:
        """Требует расширение SVG для результата."""
        values = self._valid_values()
        values["output_file"] = "graph.png"
        with self.assertRaises(ConfigurationError):
            self._load(values)

    def test_missing_parameter_error(self) -> None:
        """Сообщает об отсутствующем обязательном ключе."""
        values = self._valid_values()
        del values["package_name"]
        with self.assertRaises(ConfigurationError):
            self._load(values)


if __name__ == "__main__":
    unittest.main()
