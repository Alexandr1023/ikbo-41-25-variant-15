"""Чтение и проверка пользовательской конфигурации."""

from configparser import ConfigParser, Error as ConfigParserError
from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Ошибка чтения или проверки параметров приложения."""


@dataclass(frozen=True)
class AppConfig:
    """Параметры запуска инструмента."""

    package_name: str
    source: str
    test_mode: bool
    output_file: Path


def _read_ini(path: Path) -> ConfigParser:
    parser = ConfigParser(interpolation=None)
    try:
        with path.open("r", encoding="utf-8") as config_file:
            parser.read_file(config_file)
    except OSError as error:
        raise ConfigurationError(
            f"Не удалось открыть файл конфигурации: {path}"
        ) from error
    except (ConfigParserError, UnicodeError) as error:
        raise ConfigurationError(
            f"Некорректный файл INI: {error}"
        ) from error
    return parser


def _required_values(parser: ConfigParser) -> dict[str, str]:
    if not parser.has_section("application"):
        raise ConfigurationError("В конфигурации нет секции [application].")
    section = parser["application"]
    keys = ("package_name", "source", "test_mode", "output_file")
    missing = [key for key in keys if not section.get(key, "").strip()]
    if missing:
        raise ConfigurationError(
            "Не заданы обязательные параметры: " + ", ".join(missing)
        )
    return {key: section[key].strip() for key in keys}


def _parse_mode(value: str) -> bool:
    normalized = value.casefold()
    if normalized not in {"true", "false"}:
        raise ConfigurationError(
            "Параметр test_mode должен быть true или false."
        )
    return normalized == "true"


def _validate_source(source: str, test_mode: bool) -> None:
    if test_mode:
        graph_file = Path(source)
        if not graph_file.is_file():
            raise ConfigurationError(
                f"Файл тестового графа не найден: {graph_file}"
            )
        return
    parsed = urlsplit(source)
    valid_web_url = parsed.scheme in {"http", "https", "git", "ssh"}
    valid_scp_url = re.match(r"^[^/@\s]+@[^:/\s]+:.+$", source)
    if not valid_web_url and not valid_scp_url:
        raise ConfigurationError(
            "Для обычного режима source должен быть URL git-репозитория."
        )
    if valid_web_url and not parsed.netloc:
        raise ConfigurationError("В URL git-репозитория отсутствует узел.")


def _validate_output(value: str) -> Path:
    output_file = Path(value)
    if not value.strip():
        raise ConfigurationError("Параметр output_file не может быть пустым.")
    if output_file.suffix.casefold() != ".svg":
        raise ConfigurationError("Файл output_file должен иметь расширение .svg.")
    return output_file


def load_config(path: Path) -> AppConfig:
    """Загружает INI-файл и проверяет каждое поле."""
    values = _required_values(_read_ini(path))
    test_mode = _parse_mode(values["test_mode"])
    if not re.fullmatch(r"[A-Za-z0-9_-]+", values["package_name"]):
        raise ConfigurationError(
            "Имя пакета должно содержать латинские буквы, цифры, _ или -."
        )
    _validate_source(values["source"], test_mode)
    return AppConfig(
        package_name=values["package_name"],
        source=values["source"],
        test_mode=test_mode,
        output_file=_validate_output(values["output_file"]),
    )


def format_config(config: AppConfig) -> str:
    """Возвращает все параметры в формате ключ-значение."""
    values = (
        ("имя_пакета", config.package_name),
        ("источник", config.source),
        ("тестовый_режим", str(config.test_mode).lower()),
        ("файл_вывода", str(config.output_file)),
    )
    return "\n".join(f"{key}={value}" for key, value in values)

