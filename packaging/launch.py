"""PyInstaller 진입점. `python -m sukpago`와 같은 일을 한다."""

from sukpago.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
