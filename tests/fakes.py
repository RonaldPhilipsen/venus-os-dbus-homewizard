"""Test doubles with the same narrow API as the real Venus OS classes."""

from typing import Any, Dict, Iterable


class FakeService:
    """Stands in for vedbus.VeDbusService.

    It has only [] get and [] set, as VeDbusService has. Both raise KeyError
    for a path that was not added, so code that needs a dict-only method
    such as .get fails in the tests too.
    """

    def __init__(self, paths: Iterable[str] = ()) -> None:
        self.values: Dict[str, Any] = {path: None for path in paths}

    def __getitem__(self, path: str) -> Any:
        return self.values[path]

    def __setitem__(self, path: str, value: Any) -> None:
        if path not in self.values:
            raise KeyError(path)
        self.values[path] = value
