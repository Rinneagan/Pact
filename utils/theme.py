"""
Namida theme color system for Pact PDF application.
Provides color tokens as (light_mode, dark_mode) tuples for CustomTkinter.
"""

class NamidaTheme:
    BG_MAIN = ("#F3F6FA", "#0A0D14")
    BG_SIDEBAR = ("#FFFFFF", "#000000")
    BG_CARD = ("#FFFFFF", "#141A29")
    BG_CARD_SECONDARY = ("#F9FAFC", "#1C253B")
    
    ACCENT_PRIMARY = ("#00A3C4", "#00E5FF")
    ACCENT_SECONDARY = ("#7A00E0", "#9D00FF")
    ACCENT_HOVER = ("#E2ECF7", "#1D283C")
    
    BORDER = ("#D8E2ED", "#202A3C")
    
    TEXT_PRIMARY = ("#1C2533", "#FFFFFF")
    TEXT_MUTED = ("#6A7B95", "#8A95A5")


import customtkinter as ctk
import tkinter as tk
import math
from typing import Callable

class NamidaThemeToggle(ctk.CTkCanvas):
    """An animated, highly visual sun/moon theme switch canvas."""

    def __init__(self, master, is_dark: bool, command: Callable[[bool], None], **kwargs):
        bg_canvas = "#000000" if is_dark else "#FFFFFF"
        super().__init__(master, width=70, height=30, highlightthickness=0, bg=bg_canvas, cursor="hand2", **kwargs)
        self.is_dark = is_dark
        self.command = command
        self.knob_x = 53 if is_dark else 17
        self.animating = False
        
        self.bind("<Button-1>", self._on_click)
        self.draw()

    def draw(self):
        self.delete("all")
        bg_canvas = "#000000" if self.is_dark else "#FFFFFF"
        self.configure(bg=bg_canvas)
        
        # Draw pill track
        track_color = "#141A29" if self.is_dark else "#F3F6FA"
        self.create_oval(5, 5, 25, 25, fill=track_color, outline="")
        self.create_oval(45, 5, 65, 25, fill=track_color, outline="")
        self.create_rectangle(15, 5, 55, 25, fill=track_color, outline="")
        
        if self.is_dark:
            # Draw tiny glowing stars in track background
            self.create_oval(18, 10, 20, 12, fill="#9D00FF", outline="")
            self.create_oval(34, 18, 36, 20, fill="#00E5FF", outline="")
            self.create_oval(25, 8, 27, 10, fill="#FFFFFF", outline="")
            
            # Draw Moon knob
            self.create_oval(self.knob_x - 10, 5, self.knob_x + 10, 25, fill="#00E5FF", outline="")
            # Crescent cutout using track color
            self.create_oval(self.knob_x - 15, 3, self.knob_x + 4, 22, fill=track_color, outline="")
        else:
            # Draw soft white clouds in track background
            self.create_oval(45, 12, 53, 20, fill="#FFFFFF", outline="")
            self.create_oval(38, 14, 48, 22, fill="#FFFFFF", outline="")
            
            # Draw Sun knob
            self.create_oval(self.knob_x - 10, 5, self.knob_x + 10, 25, fill="#FFB300", outline="")
            # Sun rays
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                x1 = self.knob_x + int(6 * math.cos(rad))
                y1 = 15 + int(6 * math.sin(rad))
                x2 = self.knob_x + int(11 * math.cos(rad))
                y2 = 15 + int(11 * math.sin(rad))
                self.create_line(x1, y1, x2, y2, fill="#FF8F00", width=1.5)
                
            # Inner sun circle
            self.create_oval(self.knob_x - 6, 9, self.knob_x + 6, 21, fill="#FFD54F", outline="")

    def _on_click(self, event):
        if self.animating:
            return
        self.animating = True
        self.is_dark = not self.is_dark
        target_x = 53 if self.is_dark else 17
        self._animate_slide(target_x)

    def _animate_slide(self, target_x):
        step = 6 if target_x > self.knob_x else -6
        if abs(target_x - self.knob_x) <= abs(step):
            self.knob_x = target_x
            self.draw()
            self.animating = False
            self.command(self.is_dark)
        else:
            self.knob_x += step
            self.draw()
            self.after(15, lambda: self._animate_slide(target_x))
