"""Version information shown in Help → About."""
import os
import subprocess

VERSION = '1.1.0'
# the underrail.exe the extracted data (data/*.json) and the formulas read from its IL come from
TARGET_GAME_VERSION = '1.3.1.2'
AUTHOR = 'Chromdioxyde'
LICENSE = 'GNU GPL v3 or later'  # full text in LICENSE
LICENSE_URL = 'https://www.gnu.org/licenses/gpl-3.0.html'

_HERE = os.path.dirname(os.path.abspath(__file__))


def commit():
    """Short git commit of this build: commit.txt written by the install/AppImage scripts, else git, else None."""
    try:
        with open(os.path.join(_HERE, 'commit.txt')) as f:
            return f.read().strip() or None
    except OSError:
        pass
    try:
        out = subprocess.run(['git', '-C', _HERE, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True,
                             timeout=2)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None
