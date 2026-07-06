"""能力实现注册表。

维护 ``name -> impl_cls`` 映射。``@register_capability(name)`` 装饰注册，
``get_capability_impl(name)`` 查表实例化。新增实现仅需新文件加装饰并 import 触发注册。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_CAPABILITY_IMPLS: dict[str, type] = {}


def register_capability(name: str) -> Callable[[type], type]:
    """装饰器：注册能力实现类到全局表。"""

    def decorator(cls: type) -> type:
        if name in _CAPABILITY_IMPLS and _CAPABILITY_IMPLS[name] is not cls:
            import logging

            logging.getLogger(__name__).warning(
                "capability impl '%s' re-registered: %s -> %s",
                name,
                _CAPABILITY_IMPLS[name].__name__,
                cls.__name__,
            )
        _CAPABILITY_IMPLS[name] = cls
        return cls

    return decorator


def get_capability_impl(name: str) -> type:
    """按名查能力实现类，未注册抛 KeyError。"""
    if name not in _CAPABILITY_IMPLS:
        raise KeyError(
            f"capability impl '{name}' not registered. "
            f"Available: {sorted(_CAPABILITY_IMPLS)}"
        )
    return _CAPABILITY_IMPLS[name]


def list_capability_impls() -> list[str]:
    """列出所有已注册能力实现名。"""
    return sorted(_CAPABILITY_IMPLS)


def clear_registry() -> None:
    """清空注册表，用于测试隔离。"""
    _CAPABILITY_IMPLS.clear()
