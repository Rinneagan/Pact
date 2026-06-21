import tkinter as tk
from typing import Any

import customtkinter as ctk

from utils.typography import PremiumTypography
from utils.theme import NamidaTheme
from utils.icons import NamidaIcons


class ReadingStatsManager:
    """Manages the reading statistics display in the sidebar."""

    def __init__(self, app):
        self.app = app
        self.stats_frame = None

    def setup_ui(self, sidebar_frame):
        """Set up the reading stats UI in the sidebar."""
        self.stats_frame = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
        self.stats_frame.grid(row=5, column=0, padx=20, pady=(0, 8), sticky="ew")
        self.stats_frame.grid_columnconfigure(0, weight=1)

    def refresh_reading_stats(self) -> None:
        """Refresh the reading statistics display."""
        if not hasattr(self, "stats_frame"):
            return
        for widget in self.stats_frame.winfo_children():
            widget.destroy()

        finished_count = self.app.stats_store.documents_finished_this_month()
        longest = self.app.stats_store.longest_read()
        daily = self.app.stats_store.last_n_days_pages(7)

        title_frame = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w", pady=(0, 4))
        
        ctk.CTkLabel(
            title_frame, text="",
            image=NamidaIcons.get("notes", size=14, light_color=NamidaTheme.TEXT_MUTED[0], dark_color=NamidaTheme.TEXT_MUTED[1])
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            title_frame, text="Reading Log",
            font=PremiumTypography.display_small(size=12),
            text_color=NamidaTheme.TEXT_MUTED,
        ).pack(side="left")

        if finished_count == 0 and not longest:
            summary = "Nothing finished yet"
        else:
            summary = f"{finished_count} finished this month"
            if longest:
                title, pages = longest
                short_title = title if len(title) <= 18 else title[:15] + "…"
                summary += f"\nLongest: {short_title} ({pages}p)"

        ctk.CTkLabel(
            self.stats_frame, text=summary,
            font=PremiumTypography.body_small(size=11),
            text_color=NamidaTheme.TEXT_MUTED, anchor="w", justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, 6))

        sparkline = self.draw_sparkline(self.stats_frame, daily)
        sparkline.grid(row=2, column=0, sticky="w")

    def draw_sparkline(self, parent: Any, values: list[int]) -> tk.Canvas:
        """Draw a sparkline chart showing pages read over the last N days."""
        width, height, bar_w, gap = 168, 28, 16, 4
        bg = NamidaTheme.BG_SIDEBAR[1] if self.app.is_dark_theme else NamidaTheme.BG_SIDEBAR[0]
        primary_color = NamidaTheme.ACCENT_PRIMARY[1] if self.app.is_dark_theme else NamidaTheme.ACCENT_PRIMARY[0]
        secondary_color = NamidaTheme.ACCENT_SECONDARY[1] if self.app.is_dark_theme else NamidaTheme.ACCENT_SECONDARY[0]

        canvas = tk.Canvas(parent, width=width, height=height, highlightthickness=0, bg=bg)
        max_val = max(values) if max(values) > 0 else 1
        for i, v in enumerate(values):
            bar_h = max(2, int((v / max_val) * (height - 4))) if v > 0 else 0
            x0 = i * (bar_w + gap)
            x1 = x0 + bar_w
            y1 = height
            y0 = height - bar_h if v > 0 else height - 2
            
            # Use secondary color (purple) for normal read days, primary (cyan) for the max reading day
            is_max = (v == max(values) and v > 0)
            fill_color = primary_color if is_max else (secondary_color if v > 0 else NamidaTheme.BORDER[1] if self.app.is_dark_theme else NamidaTheme.BORDER[0])
            canvas.create_rectangle(x0, y0, x1, y1, fill=fill_color, outline="")
        return canvas
