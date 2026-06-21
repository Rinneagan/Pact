"""
Typography system for Pact PDF application.
Provides cached, consistent fonts for the UI.
"""

from __future__ import annotations

import os
import tkinter.font as tkfont

import customtkinter as ctk


class PremiumTypography:
    """Cached typography system for consistent, modern fonts."""

    GEOMETRIC_FONT_FAMILY: str = "BBH Hegarty"
    MONOSPACE_FONT_FAMILY: str = "BBH Hegarty"
    DISPLAY_FONT_FAMILY: str = "BBH Hegarty"

    _cache: dict[tuple, ctk.CTkFont] = {}
    _display_font_loaded: bool = False

    @classmethod
    def load_display_font(cls) -> None:
        """Load the bundled BBH Hegarty font from assets/fonts/."""
        if cls._display_font_loaded:
            return

        font_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
        font_files = {
            "BBHHegarty-Regular": "BBHHegarty-Regular.ttf",
        }

        fonts_added = 0
        for font_name, filename in font_files.items():
            font_path = os.path.join(font_dir, filename)
            if os.path.exists(font_path):
                if os.name == "nt":
                    try:
                        import ctypes
                        # AddFontResourceW returns > 0 if successful
                        num_added = ctypes.windll.gdi32.AddFontResourceW(font_path)
                        if num_added > 0:
                            fonts_added += num_added
                    except Exception:
                        pass

        font_path = os.path.join(font_dir, "BBHHegarty-Regular.ttf")
        if os.path.exists(font_path):
            cls.DISPLAY_FONT_FAMILY = "BBH Hegarty"
            cls.GEOMETRIC_FONT_FAMILY = "BBH Hegarty"
            cls.MONOSPACE_FONT_FAMILY = "BBH Hegarty"
        else:
            cls.DISPLAY_FONT_FAMILY = "Georgia"
            cls.GEOMETRIC_FONT_FAMILY = "Georgia"
            cls.MONOSPACE_FONT_FAMILY = "Georgia"

        if os.name == "nt" and fonts_added > 0:
            try:
                import ctypes
                # Notify system about font changes
                ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0) # HWND_BROADCAST, WM_FONTCHANGE
            except Exception:
                pass

        # Monkeypatch CustomTkinter's CTkFont constructor to force BBH Hegarty as the default family
        try:
            import customtkinter as ctk
            original_init = ctk.CTkFont.__init__
            
            def patched_init(self, *args, **kwargs):
                if "family" not in kwargs or kwargs["family"] in ("Segoe UI", "Consolas", "Courier New", "Arial", "Courier", "Helvetica", "Times New Roman"):
                    kwargs["family"] = cls.DISPLAY_FONT_FAMILY
                original_init(self, *args, **kwargs)
                
            ctk.CTkFont.__init__ = patched_init
        except Exception:
            pass

        # Patch default system fonts in standard Tkinter
        try:
            import tkinter.font as tkfont
            for font_name in (
                "TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont",
                "TkHeadingFont", "TkCaptionFont", "TkTooltipFont", "TkIconFont"
            ):
                try:
                    f = tkfont.nametofont(font_name)
                    f.configure(family=cls.DISPLAY_FONT_FAMILY)
                except Exception:
                    pass
        except Exception:
            pass

        cls._display_font_loaded = True

    @classmethod
    def _get(cls, family: str, size: int, weight: str) -> ctk.CTkFont:
        key = (family, size, weight)
        if key not in cls._cache:
            cls._cache[key] = ctk.CTkFont(family=family, size=size, weight=weight)
        return cls._cache[key]

    @classmethod
    def heading_large(cls, size: int = 28, weight: str = "normal") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def heading_medium(cls, size: int = 18, weight: str = "normal") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def heading_small(cls, size: int = 16, weight: str = "normal") -> ctk.CTkFont:
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
    def button_text(cls, size: int = 14, weight: str = "normal") -> ctk.CTkFont:
        return cls._get(cls.GEOMETRIC_FONT_FAMILY, size, weight)

    @classmethod
    def display_large(cls, size: int = 32, weight: str = "normal") -> ctk.CTkFont:
        """Display font for wordmark and large headings."""
        return cls._get(cls.DISPLAY_FONT_FAMILY, size, weight)

    @classmethod
    def display_medium(cls, size: int = 20, weight: str = "normal") -> ctk.CTkFont:
        """Display font for section headers."""
        return cls._get(cls.DISPLAY_FONT_FAMILY, size, weight)

    @classmethod
    def display_small(cls, size: int = 16, weight: str = "normal") -> ctk.CTkFont:
        """Display font for small section headers and labels."""
        return cls._get(cls.DISPLAY_FONT_FAMILY, size, weight)
