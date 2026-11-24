"""Чтение метаданных crates.io через его публичный sparse index."""

import json
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


def _version_parts(value: str) -> tuple[int, int, int, str]:
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
    major, minor, patch, pre = _version_parts(value)
    return major, minor, patch, not bool(pre), pre


def _constraint_matches(version: str, raw: str) -> bool:
    requirement = raw.strip()
    if requirement in {"", "*"}:
        return True
    match = _CONSTRAINT.fullmatch(requirement)
    if not match:
        raise DependencyGraphError(
            f"Неподдерживаемое требование версии Cargo: {raw}"
        )
    operator, major_text, minor_text, patch_text, pre = match.groups()
    parts = (major_text, minor_text, patch_text)
    numeric = [int(item) if item and item.isdigit() else 0 for item in parts]
    precision = 1 + sum(item is not None for item in parts[1:])
    if any(item in {"*", "x", "X"} for item in parts):
        return _wildcard_matches(version, parts)
    candidate = _version_key(version)
    target_text = ".".join(str(item) for item in numeric)
    if pre:
        target_text += f"-{pre}"
    target = _version_key(target_text)
    operation = operator or "^"
    if operation in {"=", "=="}:
        return candidate == target
    if operation == ">=":
        return candidate >= target
    if operation == ">":
        return candidate > target
    if operation == "<=":
        return candidate <= target
    if operation == "<":
        return candidate < target
    if operation == "~":
        upper = (numeric[0] + 1, 0, 0) if precision == 1 else (
            numeric[0], numeric[1] + 1, 0
        )
    elif precision == 1:
        upper = (numeric[0] + 1, 0, 0)
    elif precision == 2 and numeric[0] == 0 and numeric[1] == 0:
        upper = (0, 1, 0)
    elif numeric[0]:
        upper = (numeric[0] + 1, 0, 0)
    elif numeric[1]:
        upper = (0, numeric[1] + 1, 0)
    else:
        upper = (0, 0, numeric[2] + 1)
    return candidate >= target and candidate[:3] < upper


def _wildcard_matches(version: str, parts: tuple) -> bool:
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
    name = crate_name.lower()
    if not re.fullmatch(r"[a-z0-9_-]+", name):
        raise DependencyGraphError(f"Некорректное имя crate: {crate_name}")
    if len(name) == 1:
        return f"1/{name}"
    if len(name) == 2:
        return f"2/{name}"
    if len(name) == 3:
        return f"3/{name[0]}/{name}"
    return f"{name[:2]}/{name[2:4]}/{name}"


class CrateIndex:
    """Загружает и кэширует строки sparse index для crate."""

    def __init__(self) -> None:
        self._cache: dict[str, list[dict]] = {}

    def _records(self, name: str) -> list[dict]:
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

