from poirot.backend.app.cli.banner import render_banner


def test_banner_uses_macintosh_gradient_pixel_style() -> None:
    banner = render_banner("POIROT")

    # Truecolor top gradient #FFB347 = (255, 179, 71)
    assert "\x1b[38;2;255;179;71m" in banner
    # Truecolor bottom gradient #FFD700 = (255, 215, 0)
    assert "\x1b[38;2;255;215;0m" in banner
    # Box-drawing pixel font
    assert "█" in banner
    # Version line
    assert "v1.0.0" in banner
    # Tagline rendered in italic
    assert "The little grey cells are working..." in banner
    assert "\x1b[3m" in banner
    # Decorations removed: no separators, smiley, or magnifier
    assert "♦" not in banner
    assert "★" not in banner
    assert ":-)" not in banner
    assert "( * )" not in banner
