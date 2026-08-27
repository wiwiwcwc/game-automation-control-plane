"""PyInstaller entry point kept outside the application package."""

from game_control_plane.app import main


if __name__ == "__main__":
    raise SystemExit(main())
