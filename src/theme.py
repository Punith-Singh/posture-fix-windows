# theme.py – Simple theme management for PostureFix dashboard
import tkinter as tk
from tkinter import ttk

# Define two basic themes. Colors are chosen to match existing palette but provide light variant.
DARK_THEME = {
    "COLOR_BG": "#1e1e2e",
    "COLOR_SURFACE": "#2a2a3d",
    "COLOR_CARD": "#313148",
    "COLOR_TEXT": "#e0e0e8",
    "COLOR_TEXT_DIM": "#8888a0",
    "COLOR_GREEN": "#2ecc71",
    "COLOR_RED": "#e74c3c",
    "COLOR_AMBER": "#f39c12",
    "COLOR_BLUE": "#3498db",
    "COLOR_ACCENT": "#0078D7",
    "COLOR_CHART_BG": "#252538",
}

LIGHT_THEME = {
    "COLOR_BG": "#ffffff",
    "COLOR_SURFACE": "#f0f0f0",
    "COLOR_CARD": "#e0e0e0",
    "COLOR_TEXT": "#202020",
    "COLOR_TEXT_DIM": "#606060",
    "COLOR_GREEN": "#2ecc71",
    "COLOR_RED": "#e74c3c",
    "COLOR_AMBER": "#f39c12",
    "COLOR_BLUE": "#3498db",
    "COLOR_ACCENT": "#0078D7",
    "COLOR_CHART_BG": "#f9f9f9",
}

def apply_theme(root, theme_dict):
    """Apply the given theme to the Tk root and ttk styles.

    Args:
        root: The Tk root window.
        theme_dict: Dictionary containing color keys as defined above.
    """
    # Update root background
    root.configure(bg=theme_dict["COLOR_BG"])

    style = ttk.Style(root)
    style.theme_use("clam")
    # Generic widget style
    style.configure(".", background=theme_dict["COLOR_BG"], foreground=theme_dict["COLOR_TEXT"], fieldbackground=theme_dict["COLOR_SURFACE"]) 
    style.configure("TFrame", background=theme_dict["COLOR_BG"])
    style.configure("TLabel", background=theme_dict["COLOR_BG"], foreground=theme_dict["COLOR_TEXT"])
    style.configure("TButton", background=theme_dict["COLOR_ACCENT"], foreground="white", padding=6)
    style.map("TButton", background=[("active", "#005a9e")])
    style.configure("Card.TFrame", background=theme_dict["COLOR_CARD"])
    style.configure("Card.TLabel", background=theme_dict["COLOR_CARD"], foreground=theme_dict["COLOR_TEXT"])
    style.configure("green.Horizontal.TProgressbar", troughcolor=theme_dict["COLOR_BG"], background=theme_dict["COLOR_GREEN"])
    style.configure("red.Horizontal.TProgressbar", troughcolor=theme_dict["COLOR_BG"], background=theme_dict["COLOR_RED"])
    # Update any manually created canvas backgrounds if needed elsewhere
    # Note: callers may need to redraw charts to reflect new background colors.
    # Return the theme dict for convenience
    return theme_dict

