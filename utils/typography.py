"""
Typography system for Pact PDF application.
Provides cached, consistent fonts for the UI.
"""

from __future__ import annotations

import customtkinter as ctk


class PremiumTypography:
    """Cached typography system for consistent, modern fonts."""

    GEOMETRIC_FONT_FAMILY: str = "Segoe UI"
    MONOSPACE_FONT_FAMILY: str = "Consolas"

    _cache: dict[tuple, ctk.CTkFont] = {}

    @classmethod
    def _get(cls, family: str, size: int, weight: str) -> ctk.CTkFont:
        key = (family, size, weight)
        if key not in cls._cache:
            cls._cache[key] = ctk.CTkFont(family=family, size=size, weight=weight)
        return cls._cache[key]

    @classmethod
    def heading_large(cls, size: int = 28, weight: str = "bold") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def heading_medium(cls, size: int = 18, weight: str = "bold") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def heading_small(cls, size: int = 16, weight: str = "bold") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def body_text(cls, size: int = 14, weight: str = "normal") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def body_small(cls, size: int = 12, weight: str = "normal") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def monospace(cls, size: int = 11, weight: str = "normal") -> ctk.CTkFont:
        return cls._get(cls.MONOSPACE_FONT_FAMILY, size, weight)

    @classmethod
    def button_text(cls, size: int = 14, weight: str = "bold") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)
