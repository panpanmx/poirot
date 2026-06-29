from __future__ import annotations


RESET = "\x1b[0m"
ITALIC = "\x1b[3m"

# Top-to-bottom gradient: #FFB347 (warm orange) -> #FFD700 (gold).
# 6 stops, one per pixel-font row.
_GRADIENT = [
    (255, 179, 71),   # #FFB347  row 1
    (255, 186, 57),   #          row 2
    (255, 193, 43),   #          row 3
    (255, 200, 28),   #          row 4
    (255, 207, 14),   #          row 5
    (255, 215, 0),    # #FFD700  row 6
]
_LIGHT_GOLD = (255, 232, 117)  # lighter gold #FFE875, version + tagline

# POIROT in box-drawing pixel font, 6 rows.
_PIXEL_POIROT = [
    "██████╗  ██████╗ ██╗██████╗  ██████╗ ████████╗",
    "██╔══██╗██╔═══██╗██║██╔══██╗██╔═══██╗╚══██╔══╝",
    "██████╔╝██║   ██║██║██████╔╝██║   ██║   ██║   ",
    "██╔═══╝ ██║   ██║██║██╔══██╗██║   ██║   ██║   ",
    "██║     ╚██████╔╝██║██║  ██║╚██████╔╝   ██║   ",
    "╚═╝      ╚═════╝ ╚═╝╚═╝  ╚═╝ ╚═════╝    ╚═╝   ",
]


def _fg(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"\x1b[38;2;{r};{g};{b}m"


def render_banner(text: str = "POIROT") -> str:
    upper = text.upper()
    lines: list[str] = []

    if upper == "POIROT":
        for idx, row in enumerate(_PIXEL_POIROT):
            lines.append(f"{_fg(_GRADIENT[idx])}{row}{RESET}")
    else:
        lines.append(f"{_fg(_GRADIENT[0])}{upper}{RESET}")

    lines.append("")
    lines.append(
        f"{_fg(_LIGHT_GOLD)}v1.0.0  |  {ITALIC}The little grey cells are working...{RESET}"
    )

    return "\n".join(lines)
