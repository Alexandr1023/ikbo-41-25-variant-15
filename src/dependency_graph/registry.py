"""Чтение метаданных crates.io через его публичный sparse index."""

import json
from operator import eq, ge, gt, le, lt
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dependency_graph.cargo import Dependency
from dependency_graph.errors import DependencyGraphError

_VERSION = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+.*)?$"
)
_CONSTRAINT = re.compile(
    r"^(\^|~|>=|<=|>|<|=)?\s*v?(\d+)"
    r"(?:\.(\d+|\*|x|X))?(?:\.(\d+|\*|x|X))?"
    r"(?:-([0-9A-Za-z.-]+))?$"
)
ONE_COMPONENT = 1
TWO_COMPONENTS = 2
ONE_CHARACTER = 1
TWO_CHARACTERS = 2
THREE_CHARACTERS = 3
ZERO_VERSION = 0
NEXT_COMPONENT = 1
_COMPARATORS = {
    "=": eq,
    ">=": ge,
    ">": gt,
    "<=": le,
    "<": lt,
}


def _version_parts(value: str) -> tuple[int, int, int, str]:
    """Разбирает SemVer в числовые компоненты и prerelease."""
    match = _VERSION.fullmatch(value)
    if not match:
        raise ValueError(f"Некорректная версия: {value}")
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        match.group(4) or "",
    )


def _version_key(value: str) -> tuple:
    """Возвращает ключ для сортировки SemVer."""
    major, minor, patch, pre = _version_parts(value)
    return major, minor, patch, not bool(pre), pre


def _constraint_parts(raw: str) -> tuple:
    """Разбирает оператор, границы и wildcard требования."""
    requirement = raw.strip()
    match = _CONSTRAINT.fullmatch(requirement)
    if not match:
        raise DependencyGraphError(
            f"Неподдерживаемое требование версии Cargo: {raw}"
        )
    operator, major_text, minor_text, patch_text, pre = match.groups()
    parts = (major_text, minor_text, patch_text)
    numeric = [int(item) if item and item.isdigit() else 0 for item in parts]
    precision = 1 + sum(item is not None for item in parts[1:])
    has_wildcard = any(item in {"*", "x", "X"} for item in parts)
    return (
        operator or "^",
        tuple(numeric),
        precision,
        pre,
        has_wildcard,
        parts,
    )


def _upper_bound(operator: str, numbers: tuple, precision: int) -> tuple:
    """Вычисляет верхнюю исключённую границу диапазона."""
    major, minor, patch = numbers
    if operator == "~":
        if precision == ONE_COMPONENT:
            return major + 1, ZERO_VERSION, ZERO_VERSION
        return major, minor + 1, ZERO_VERSION
    if precision == ONE_COMPONENT or major != ZERO_VERSION:
        return major + 1, ZERO_VERSION, ZERO_VERSION
    if precision == TWO_COMPONENTS and minor == ZERO_VERSION:
        return ZERO_VERSION, NEXT_COMPONENT, ZERO_VERSION
    if minor != ZERO_VERSION:
        return ZERO_VERSION, minor + 1, ZERO_VERSION
    return ZERO_VERSION, ZERO_VERSION, patch + 1


def _constraint_matches(version: str, raw: str) -> bool:
    """Проверяет версию на соответствие одному требованию."""
    requirement = raw.strip()
    if requirement in {"", "*"}:
        return True
    operation, numbers, precision, pre, wildcard, parts = (
        _constraint_parts(raw)
    )
    if wildcard:
        return _wildcard_matches(version, parts)
    candidate = _version_key(version)
    target_text = ".".join(str(item) for item in numbers)
    if pre:
        target_text += f"-{pre}"
    target = _version_key(target_text)
    comparator = _COMPARATORS.get(operation)
    if comparator:
        return comparator(candidate, target)
    upper = _upper_bound(operation, numbers, precision)
    return candidate >= target and candidate[:3] < upper


def _wildcard_matches(version: str, parts: tuple) -> bool:
    """Сверяет версию с частичным wildcard-требованием."""
    candidate = _version_parts(version)
    for index, value in enumerate(parts):
        if value in {None, "*", "x", "X"}:
            return True
        if candidate[index] != int(value):
            return False
    return True


def version_matches(version: str, requirement: str) -> bool:
    """Проверяет распространённые требования semver Cargo."""
    constraints = [item.strip() for item in requirement.split(",")]
    if "-" not in requirement and _version_parts(version)[3]:
        return False
    return all(
        _constraint_matches(version, item) for item in constraints
    )


def _index_path(crate_name: str) -> str:
    """Формирует относительный путь sparse index crate."""
    name = crate_name.lower()
    if not re.fullmatch(r"[a-z0-9_-]+", name):
        raise DependencyGraphError(f"Некорректное имя crate: {crate_name}")
    if len(name) == ONE_CHARACTER:
        return f"1/{name}"
    if len(name) == TWO_CHARACTERS:
        return f"2/{name}"
    if len(name) == THREE_CHARACTERS:
        return f"3/{name[0]}/{name}"
    return f"{name[:2]}/{name[2:4]}/{name}"


class CrateIndex:
    """Загружает и кэширует строки sparse index для crate."""

    def __init__(self) -> None:
        """Создаёт индекс с пустым кэшем метаданных."""
        self._cache: dict[str, list[dict]] = {}

    def _records(self, name: str) -> list[dict]:
        """Загружает и кэширует все версии crate."""
        if name in self._cache:
            return self._cache[name]
        url = f"https://index.crates.io/{_index_path(name)}"
        request = Request(url, headers={"User-Agent": "variant15-graph/1.0"})
        try:
            with urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise DependencyGraphError(
                f"Не удалось получить метаданные crate {name}: {error}"
            ) from error
        try:
            records = [json.loads(line) for line in text.splitlines() if line]
        except json.JSONDecodeError as error:
            raise DependencyGraphError(
                f"Индекс crate {name} содержит некорректные данные."
            ) from error
        self._cache[name] = records
        return records

    def resolve(self, name: str, requirement: str) -> dict:
        """Выбирает максимальную доступную версию по требованию."""
        records = [
            item
            for item in self._records(name)
            if not item.get("yanked")
            and version_matches(item.get("vers", ""), requirement)
        ]
        if not records:
            raise DependencyGraphError(
                f"Для {name} нет версии, подходящей под {requirement!r}."
            )
        return max(records, key=lambda item: _version_key(item["vers"]))

    def exact(self, name: str, version: str) -> dict:
        """Возвращает запись точной версии из кэша индекса."""
        for item in self._records(name):
            if item.get("vers") == version:
                return item
        raise DependencyGraphError(
            f"Версия {name} {version} отсутствует в crates.io index."
        )

    @staticmethod
    def package_id(record: dict) -> str:
        """Формирует идентификатор crate с выбранной версией."""
        return f"{record['name']}@{record['vers']}"

    @staticmethod
    def dependencies(record: dict) -> tuple[Dependency, ...]:
        """Возвращает обычные и build-зависимости без optional."""
        result = []
        for item in record.get("deps", []):
            if item.get("optional") or item.get("kind") == "dev":
                continue
            name = item.get("package") or item.get("name", "")
            result.append(
                Dependency(name, item.get("req", "*"))
            )
        return tuple(result)

