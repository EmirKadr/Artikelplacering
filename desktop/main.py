"""Entry point for Artikelplacering desktop app.

During migration this module delegates to GamlaAppen.main().
Each step of the modular refactor replaces pieces of GamlaAppen
with proper modules until this file becomes the real entry point.
"""
import sys
import os

# Ensure project root is on path so both old and new modules are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from GamlaAppen import main  # noqa: E402

if __name__ == "__main__":
    main()
