"""Locates the Underrail installation and the user folder (saves, custom portraits) on Linux
(incl. Steam Deck and Flatpak Steam) and Windows (Steam, GOG), plus per-platform app folders.
Manual choices are stored in config.json and win over detection."""
import glob
import json
import os
import re
import sys

APP = 'underrail-save-editor'
STEAM_APPID = '250520'
WINDOWS = sys.platform == 'win32'


# --- app folders -------------------------------------------------------------------------

def _env_dir(var, default):
    return os.environ.get(var) or os.path.expanduser(default)


if WINDOWS:
    CONFIG_DIR = os.path.join(_env_dir('APPDATA', '~/AppData/Roaming'), APP)
    DATA_DIR = CONFIG_DIR
    CACHE_DIR = os.path.join(_env_dir('LOCALAPPDATA', '~/AppData/Local'), APP, 'cache')
else:
    CONFIG_DIR = os.path.join(_env_dir('XDG_CONFIG_HOME', '~/.config'), APP)
    DATA_DIR = os.path.join(_env_dir('XDG_DATA_HOME', '~/.local/share'), APP)
    CACHE_DIR = os.path.join(_env_dir('XDG_CACHE_HOME', '~/.cache'), APP)
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)


# --- detection ---------------------------------------------------------------------------

def is_game_dir(d):
    return bool(d) and os.path.isfile(os.path.join(d, 'underrail.exe')) and \
        os.path.isdir(os.path.join(d, 'data', 'rules', 'items'))


def is_user_dir(d):
    return bool(d) and os.path.isdir(os.path.join(d, 'Saves'))


def _steam_roots():
    if WINDOWS:
        roots = []
        try:
            import winreg
            for hive, key in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'),
                              (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam')):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        for name in ('SteamPath', 'InstallPath'):
                            try:
                                roots.append(winreg.QueryValueEx(k, name)[0])
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        roots += [r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam']
    else:
        roots = ['~/.steam/steam', '~/.local/share/Steam', '~/.steam/root',
                 '~/.var/app/com.valvesoftware.Steam/.local/share/Steam',  # Flatpak Steam
                 '~/.var/app/com.valvesoftware.Steam/data/Steam']
    out = []
    for r in roots:
        r = os.path.realpath(os.path.expanduser(r))
        if os.path.isdir(os.path.join(r, 'steamapps')) and r not in out:
            out.append(r)
    return out


def steam_libraries():
    """All Steam library folders (each containing steamapps/), from libraryfolders.vdf."""
    libs = []
    for root in _steam_roots():
        libs.append(root)
        try:
            vdf = open(os.path.join(root, 'steamapps', 'libraryfolders.vdf'), encoding='utf-8').read()
        except OSError:
            continue
        for path in re.findall(r'"path"\s+"([^"]+)"', vdf):
            path = os.path.realpath(path.replace('\\\\', '\\'))
            if path not in libs:
                libs.append(path)
    return [l for l in libs if os.path.isdir(os.path.join(l, 'steamapps'))]


def _windows_documents():
    """Real Documents folder (handles OneDrive/relocated folders)."""
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # CSIDL_PERSONAL
        if buf.value:
            return buf.value
    except Exception:
        pass
    return os.path.expanduser('~/Documents')


def _gog_dirs():
    if not WINDOWS:
        return []
    out = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\GOG.com\Games') as games:
            for i in range(winreg.QueryInfoKey(games)[0]):
                try:
                    with winreg.OpenKey(games, winreg.EnumKey(games, i)) as g:
                        name = winreg.QueryValueEx(g, 'gameName')[0]
                        if 'underrail' in name.lower():
                            out.append(winreg.QueryValueEx(g, 'path')[0])
                except OSError:
                    continue
    except (ImportError, OSError):
        pass
    return out + [r'C:\GOG Games\Underrail', r'C:\Program Files (x86)\GOG Galaxy\Games\Underrail']


def detect():
    """(game_dir, user_dir) found automatically; either may be None."""
    game = user = None
    for lib in steam_libraries():
        g = os.path.join(lib, 'steamapps', 'common', 'Underrail')
        if not game and is_game_dir(g):
            game = g
        if not WINDOWS and not user:
            # Proton prefix; Underrail has used both "Documents" and "My Documents" over time
            for docs in ('Documents', 'My Documents'):
                u = os.path.join(lib, 'steamapps', 'compatdata', STEAM_APPID, 'pfx', 'drive_c', 'users',
                                 'steamuser', docs, 'My Games', 'Underrail')
                if is_user_dir(u):
                    user = u
                    break
    if not game:
        game = next((d for d in _gog_dirs() if is_game_dir(d)), None)
    if WINDOWS and not user:
        u = os.path.join(_windows_documents(), 'My Games', 'Underrail')
        user = u if is_user_dir(u) else None
    if not WINDOWS and not user:
        # other Wine prefixes (Lutris, Heroic, Bottles): look for the usual folder layout
        for u in glob.glob(os.path.expanduser('~/**/drive_c/users/*/*/My Games/Underrail'), recursive=True):
            if is_user_dir(u):
                user = u
                break
    return game, user


_resolved = None


def resolve():
    """(game_dir, user_dir): config overrides, then environment, then detection."""
    global _resolved
    if _resolved is None:
        cfg = load_config()
        dg, du = (None, None)
        game = cfg.get('game_dir') or os.environ.get('UNDERRAIL_GAME_DIR')
        user = cfg.get('user_dir') or os.environ.get('UNDERRAIL_USER_DIR')
        if not is_game_dir(game) or not is_user_dir(user):
            dg, du = detect()
        _resolved = (game if is_game_dir(game) else dg, user if is_user_dir(user) else du)
    return _resolved


def set_dirs(game, user):
    """Store manual choices and use them from now on."""
    global _resolved
    cfg = load_config()
    cfg['game_dir'], cfg['user_dir'] = game, user
    save_config(cfg)
    _resolved = None


def game_running():
    """True if underrail.exe runs (natively on Windows, or through Wine/Proton)."""
    if WINDOWS:
        import subprocess
        try:
            out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq underrail.exe', '/NH'],
                                 capture_output=True, text=True, creationflags=0x08000000).stdout
            return 'underrail.exe' in out.lower()
        except Exception:
            return False
    for pid in os.listdir('/proc'):
        if pid.isdigit():
            try:
                cmd = open(f'/proc/{pid}/cmdline', 'rb').read().lower()
            except OSError:
                continue
            # the Proton/Wine process carries the exe path; our own processes have other names
            if b'underrail.exe' in cmd and b'underrail_' not in cmd and b'pgrep' not in cmd:
                return True
    return False
