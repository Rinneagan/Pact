"""
Dynamic vector icon renderer for Pact PDF application.
Draws anti-aliased, theme-aware line icons using PIL.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple
import customtkinter as ctk
from PIL import Image as _Image, ImageDraw as _ImageDraw
from utils.theme import NamidaTheme

# Handle Pillow version differences for anti-aliasing filter
try:
    _LANCZOS = _Image.Resampling.LANCZOS
except AttributeError:
    _LANCZOS = _Image.ANTIALIAS


class NamidaIcons:
    """Dynamic, cached vector icon loader for modern Material 3 design."""

    _cache: dict[tuple, ctk.CTkImage] = {}

    @classmethod
    def get(
        cls,
        name: str,
        size: int = 20,
        light_color: str = "#00A3C4",
        dark_color: str = "#00E5FF"
    ) -> ctk.CTkImage:
        """Returns a cached theme-aware CTkImage matching the specified icon name and size."""
        key = (name, size, light_color, dark_color)
        if key not in cls._cache:
            cls._cache[key] = cls._create_icon(name, size, light_color, dark_color)
        return cls._cache[key]

    _name_mapping = {
        "search": "search",
        "library": "books",
        "folder": "folder",
        "download": "download",
        "refresh": "refresh",
        "arrow_left": "arrow-left",
        "chevron_left": "chevron-left",
        "chevron_right": "chevron-right",
        "plus": "plus",
        "minus": "minus",
        "bookmark": "bookmark",
        "outline": "list",
        "related": "link",
        "notes": "notebook",
        "close": "x",
        "external_link": "external-link",
    }

    @classmethod
    def _colorize_image(cls, pil_img: _Image.Image, color_hex: str) -> _Image.Image:
        """Colorizes a transparent black PNG image to a specific hex color."""
        from PIL import ImageColor
        r, g, b = ImageColor.getrgb(color_hex)
        solid = _Image.new("RGBA", pil_img.size, (r, g, b, 255))
        if "A" in pil_img.getbands():
            alpha = pil_img.getchannel("A")
            solid.putalpha(alpha)
        return solid

    @classmethod
    def _create_icon(
        cls,
        name: str,
        size: int,
        light_color: str,
        dark_color: str
    ) -> ctk.CTkImage:
        """Loads a Tabler Icon from disk, colorizes, and resizes it. Falls back to vector drawing if needed."""
        mapped_name = cls._name_mapping.get(name, name)
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons")
        icon_path = os.path.join(icons_dir, f"{mapped_name}.png")
        
        try:
            if os.path.exists(icon_path):
                pil_img = _Image.open(icon_path).convert("RGBA")
                
                # Colorize for light and dark themes
                light_img = cls._colorize_image(pil_img, light_color)
                dark_img = cls._colorize_image(pil_img, dark_color)
                
                # Resize using Lanczos filter
                light_img_final = light_img.resize((size, size), resample=_LANCZOS)
                dark_img_final = dark_img.resize((size, size), resample=_LANCZOS)
                
                return ctk.CTkImage(
                    light_image=light_img_final,
                    dark_image=dark_img_final,
                    size=(size, size)
                )
        except Exception as e:
            print(f"Error loading Tabler icon '{name}': {e}. Using fallback vector drawing.")
            
        # Fallback vector drawing code (original)
        scale = 4
        canvas_size = size * scale
        light_img = cls._draw_icon_vector(name, canvas_size, scale, light_color)
        dark_img = cls._draw_icon_vector(name, canvas_size, scale, dark_color)
        light_img_final = light_img.resize((size, size), resample=_LANCZOS)
        dark_img_final = dark_img.resize((size, size), resample=_LANCZOS)
        
        return ctk.CTkImage(
            light_image=light_img_final,
            dark_image=dark_img_final,
            size=(size, size)
        )

    @classmethod
    def _draw_icon_vector(
        cls,
        name: str,
        c_size: int,
        scale: int,
        color: str
    ) -> _Image.Image:
        """Draws vector lines on a transparent background."""
        img = _Image.new("RGBA", (c_size, c_size), (0, 0, 0, 0))
        draw = _ImageDraw.Draw(img)
        
        # Calculate scaled dimensions
        lw = int(1.5 * scale) # Line thickness
        pad = 4 * scale
        center = c_size // 2
        
        # Clean helper for drawing lines
        def draw_line(x1, y1, x2, y2):
            draw.line([x1, y1, x2, y2], fill=color, width=lw, joint="round")

        if name == "search":
            # Magnifying glass
            r = int(7 * scale)
            cx, cy = center - int(2 * scale), center - int(2 * scale)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=lw)
            # Handle
            hx1 = cx + int(r * 0.707)
            hy1 = cy + int(r * 0.707)
            hx2 = c_size - pad
            hy2 = c_size - pad
            draw_line(hx1, hy1, hx2, hy2)

        elif name == "library":
            # Shelf of books: vertical bars
            bx1, by1 = pad, pad
            bx2, by2 = c_size - pad, c_size - pad
            h = by2 - by1
            w = bx2 - bx1
            
            # Draw open book sheets
            draw_line(center, by1 + int(2 * scale), center, by2)
            # Left page arc
            draw.arc([bx1, by1, center, by2 + int(6 * scale)], start=180, end=360, fill=color, width=lw)
            draw_line(bx1, by1 + int(12 * scale), bx1, by2 - int(2 * scale))
            draw_line(bx1, by2 - int(2 * scale), center, by2)
            # Right page arc
            draw.arc([center, by1, bx2, by2 + int(6 * scale)], start=180, end=360, fill=color, width=lw)
            draw_line(bx2, by1 + int(12 * scale), bx2, by2 - int(2 * scale))
            draw_line(bx2, by2 - int(2 * scale), center, by2)

        elif name == "download":
            # Tray + Down Arrow
            draw_line(pad, c_size - pad - int(5 * scale), pad, c_size - pad)
            draw_line(pad, c_size - pad, c_size - pad, c_size - pad)
            draw_line(c_size - pad, c_size - pad, c_size - pad, c_size - pad - int(5 * scale))
            # Arrow
            draw_line(center, pad, center, c_size - pad - int(8 * scale))
            draw_line(center, c_size - pad - int(8 * scale), center - int(6 * scale), c_size - pad - int(14 * scale))
            draw_line(center, c_size - pad - int(8 * scale), center + int(6 * scale), c_size - pad - int(14 * scale))

        elif name == "refresh":
            # Circular arrow
            r = (c_size - pad * 2) // 2
            draw.arc([center - r, center - r, center + r, center + r], start=45, end=315, fill=color, width=lw)
            # Arrow tip
            import math
            angle = math.radians(45)
            tx = center + int(r * math.cos(angle))
            ty = center + int(r * math.sin(angle))
            draw_line(tx, ty, tx - int(6 * scale), ty)
            draw_line(tx, ty, tx, ty - int(6 * scale))

        elif name == "folder":
            # Tabbed folder outline
            tab_w = int(12 * scale)
            tab_h = int(4 * scale)
            draw.polygon([
                (pad, pad + tab_h),
                (pad + tab_w, pad + tab_h),
                (pad + tab_w + int(3 * scale), pad + tab_h + tab_h),
                (c_size - pad, pad + tab_h + tab_h),
                (c_size - pad, c_size - pad),
                (pad, c_size - pad)
            ], outline=color, width=lw)

        elif name == "arrow_left":
            # Back arrow
            draw_line(pad, center, c_size - pad, center)
            draw_line(pad, center, pad + int(8 * scale), center - int(8 * scale))
            draw_line(pad, center, pad + int(8 * scale), center + int(8 * scale))

        elif name == "chevron_left":
            # Navigation left
            draw_line(center + int(4 * scale), pad, center - int(4 * scale), center)
            draw_line(center - int(4 * scale), center, center + int(4 * scale), c_size - pad)

        elif name == "chevron_right":
            # Navigation right
            draw_line(center - int(4 * scale), pad, center + int(4 * scale), center)
            draw_line(center + int(4 * scale), center, center - int(4 * scale), c_size - pad)

        elif name == "plus":
            draw_line(pad, center, c_size - pad, center)
            draw_line(center, pad, center, c_size - pad)

        elif name == "minus":
            draw_line(pad, center, c_size - pad, center)

        elif name == "bookmark":
            # Hanging ribbon shape
            bx2 = c_size - pad - int(4 * scale)
            bx1 = pad + int(4 * scale)
            draw.polygon([
                (bx1, pad),
                (bx2, pad),
                (bx2, c_size - pad),
                (center, c_size - pad - int(10 * scale)),
                (bx1, c_size - pad)
            ], outline=color, width=lw)

        elif name == "outline":
            # 3 list item bullet points + lines
            bx = pad + int(2 * scale)
            lx = pad + int(10 * scale)
            lw_item = c_size - pad
            for y_off in [pad + int(2 * scale), center, c_size - pad - int(2 * scale)]:
                draw.ellipse([bx - int(2 * scale), y_off - int(2 * scale), bx + int(2 * scale), y_off + int(2 * scale)], fill=color)
                draw_line(lx, y_off, lw_item, y_off)

        elif name == "related":
            # Two linked circle rings
            r = int(8 * scale)
            offset = int(5 * scale)
            draw.ellipse([center - r - offset, center - r - offset, center + r - offset, center + r - offset], outline=color, width=lw)
            draw.ellipse([center - r + offset, center - r + offset, center + r + offset, center + r + offset], outline=color, width=lw)
            # Link diagonal connector
            draw_line(center - offset // 2, center - offset // 2, center + offset // 2, center + offset // 2)

        elif name == "notes":
            # Notepad page
            rx1 = pad + int(2 * scale)
            rx2 = c_size - pad - int(2 * scale)
            draw.rounded_rectangle([rx1, pad, rx2, c_size - pad], radius=int(4 * scale), outline=color, width=lw)
            # Notebook page lines
            draw_line(rx1 + int(6 * scale), pad + int(10 * scale), rx2 - int(6 * scale), pad + int(10 * scale))
            draw_line(rx1 + int(6 * scale), center, rx2 - int(6 * scale), center)
            draw_line(rx1 + int(6 * scale), c_size - pad - int(10 * scale), rx2 - int(6 * scale), c_size - pad - int(10 * scale))

        elif name == "close":
            # Cross "X" dismiss icon
            draw_line(pad, pad, c_size - pad, c_size - pad)
            draw_line(c_size - pad, pad, pad, c_size - pad)

        elif name == "external_link":
            # ↗ Link box and arrow
            draw_line(center, pad, pad, pad)
            draw_line(pad, pad, pad, c_size - pad)
            draw_line(pad, c_size - pad, c_size - pad, c_size - pad)
            draw_line(c_size - pad, c_size - pad, c_size - pad, center)
            # Arrow
            draw_line(center - int(3 * scale), center + int(3 * scale), c_size - pad, pad)
            draw_line(c_size - pad - int(8 * scale), pad, c_size - pad, pad)
            draw_line(c_size - pad, pad, c_size - pad, pad + int(8 * scale))
            
        else:
            # Fallback circle placeholder
            draw.ellipse([pad, pad, c_size - pad, c_size - pad], outline=color, width=lw)

        return img
