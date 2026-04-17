"""
Background execution helpers.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable


class BackgroundRunner:
    """
    Executes sync or async callables in a unified way.
    """

    async def run(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        result = func(*args, **kwargs)

        if inspect.isawaitable(result):
            return await result

        return result