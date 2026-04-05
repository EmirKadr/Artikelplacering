"""Entry point for Artikelplacering desktop app."""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desktop.app import main  # noqa: E402

if __name__ == "__main__":
    main()
