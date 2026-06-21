"""Entry point for the standalone PyInstaller build (see build-exe.bat).

PyInstaller freezes this single script into aread.exe. It just hands off to the
package's CLI main(); kept at repo root so PyInstaller can analyze the whole
ai_assistant_reader package via --paths src.
"""

from ai_assistant_reader.cli import main

if __name__ == "__main__":
    main()
