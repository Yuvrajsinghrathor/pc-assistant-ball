"""
PC Personal Assistant - floating ball (Windows first)
Run:  python assistant.py

Features
- Floating 3D-style ball (shape / colour / size / photo) or a character avatar
- Text + voice commands (open apps/sites, play YouTube, find files, Gmail, volume, brightness)
- Clipboard history (text + screenshots)
- PDF <-> JPG
- Select text anywhere -> click the ball -> translate popup (change language live, replace text)
"""
import sys, os, re, json, time, math, imaplib, email, subprocess, threading, webbrowser
import hashlib, contextlib, ctypes, shutil
from ctypes import wintypes
from datetime import datetime
from email.header import decode_header
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from PyQt6.QtCore import (Qt, pyqtSignal, QTimer, QSize, QBuffer, QByteArray, QIODevice,
                          QPointF, QRectF, QMimeData)
from PyQt6.QtGui import (QPainter, QColor, QPixmap, QBrush, QPen, QPainterPath, QAction,
                         QIcon, QImage, QRadialGradient, QLinearGradient, QPolygonF)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTextEdit, QListWidget, QListWidgetItem, QListView, QTabWidget, QSlider, QLabel,
    QMenu, QColorDialog, QInputDialog, QFileDialog, QMessageBox, QDialog, QComboBox,
)

IS_WIN = sys.platform == "win32"


def resource_path(rel):
    """Works both when running the .py and inside a PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return Path(base) / rel


AVATAR_DIR = resource_path("avatars")

CONFIG_FILE = Path.home() / ".pc_assistant.json"
DEFAULTS = {
    "size": 80, "color": "#6C5CE7", "x": 100, "y": 200, "image": "",
    "shape": "circle", "style3d": True, "avatar": "", "translate_to": "hi",
    "gmail_user": "", "gmail_app_password": "", "speak": True,
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


CFG = load_config()

# ---------------------------------------------------------------- helpers
SITES = {
    "youtube": "https://www.youtube.com", "yt": "https://www.youtube.com",
    "you tube": "https://www.youtube.com", "gmail": "https://mail.google.com",
    "google": "https://www.google.com", "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com", "insta": "https://www.instagram.com",
    "facebook": "https://www.facebook.com", "fb": "https://www.facebook.com",
    "github": "https://github.com", "chatgpt": "https://chatgpt.com",
    "gpt": "https://chatgpt.com", "claude": "https://claude.ai",
    "maps": "https://maps.google.com", "google maps": "https://maps.google.com",
    "drive": "https://drive.google.com", "google drive": "https://drive.google.com",
    "linkedin": "https://www.linkedin.com", "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.in", "flipkart": "https://www.flipkart.com",
}
APPS = {
    "notepad": "notepad", "calculator": "calc", "paint": "mspaint",
    "chrome": "chrome", "word": "winword", "excel": "excel",
    "powerpoint": "powerpnt", "vscode": "code", "explorer": "explorer",
}


def speak(text):
    if not CFG.get("speak"):
        return
    def run():
        try:
            import pyttsx3
            eng = pyttsx3.init()
            eng.say(text[:300])
            eng.runAndWait()
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


BROWSERS = {
    "brave": [r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
              r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
              r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"],
    "chrome": [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
               r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
               r"%LocalAppData%\Google\Chrome\Application\chrome.exe"],
    "edge": [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
             r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"],
    "firefox": [r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
                r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"],
}


BROWSER_ALIASES = {
    "chrom": "chrome", "google chrome": "chrome", "chrome browser": "chrome",
    "brave browser": "brave", "microsoft edge": "edge", "mozilla firefox": "firefox",
    "fire fox": "firefox",
}
_BROWSER_EXE = {"brave": "brave.exe", "chrome": "chrome.exe", "edge": "msedge.exe", "firefox": "firefox.exe"}


def find_browser(name):
    """Full path of the exact browser asked for (never a different one), or None."""
    for pat in BROWSERS.get(name, []):
        p = os.path.expandvars(pat)
        if os.path.exists(p):
            return p
    try:                                    # installed in a custom folder? Windows knows via App Paths
        import winreg
        exe = _BROWSER_EXE.get(name)
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\%s" % exe) as k:
                    p = winreg.QueryValueEx(k, None)[0].strip('"')
                    if os.path.exists(p):
                        return p
            except OSError:
                continue
    except Exception:
        pass
    return None


def open_url(url, browser=None, profile_dir=None):
    """Open a link in the named browser (brave/chrome/...) or in the default one.
    profile_dir = Chromium profile folder name such as 'Default' or 'Profile 1' (= one Google account)."""
    exe = find_browser(browser) if browser else None
    if exe:
        args = [exe]
        if profile_dir:
            args.append(f"--profile-directory={profile_dir}")
        subprocess.Popen(args + [url])
    else:
        webbrowser.open(url)


_PROFILE_ROOTS = {
    "chrome": r"%LocalAppData%\Google\Chrome\User Data",
    "brave": r"%LocalAppData%\BraveSoftware\Brave-Browser\User Data",
    "edge": r"%LocalAppData%\Microsoft\Edge\User Data",
}


def browser_profiles(browser):
    """[(folder, display name, signed-in email), ...] for Chrome / Brave / Edge."""
    root = _PROFILE_ROOTS.get(browser)
    if not root:
        return []
    try:
        data = json.loads((Path(os.path.expandvars(root)) / "Local State").read_text(encoding="utf-8"))
        info = data.get("profile", {}).get("info_cache", {})
    except Exception:
        return []
    return sorted((d, v.get("name", d), v.get("user_name", "")) for d, v in info.items())


def describe_profiles(browser):
    profs = browser_profiles(browser)
    if not profs:
        return f"{browser.capitalize()}: koi profile nahi mila"
    lines = [f"{browser.capitalize()} profiles:"]
    for d, name, mail in profs:
        lines.append(f"  - {name}" + (f"  ({mail})" if mail else "") + f"   [{d}]")
    return "\n".join(lines)


def resolve_profile(browser, query):
    """Match 'work', 'john@gmail.com', 'profile 2' or '2' to a profile folder -> (folder, label, error)."""
    profs = browser_profiles(browser)
    if not profs:
        return None, None, f"{browser.capitalize()} ke profiles padh nahi paya."
    q = query.strip().lower()
    hits = [p for p in profs if q in (p[0].lower(), p[1].lower(), p[2].lower())]
    if not hits and q.isdigit():
        hits = [p for p in profs if p[0].lower() == f"profile {q}"]
    if not hits:
        hits = [p for p in profs if q in p[1].lower() or q in p[2].lower()]
    if len(hits) == 1:
        d, name, mail = hits[0]
        return d, name + (f" / {mail}" if mail else ""), None
    why = "kai profiles match hue, thoda aur saaf bolo" if hits else f"'{query}' naam ka profile nahi mila"
    return None, None, why + ".\n" + describe_profiles(browser)


def app_exists(cmd):
    """True if Windows can start this program by name (avoids the 'Windows cannot find' popup)."""
    if shutil.which(cmd) or shutil.which(cmd + ".exe"):
        return True
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                winreg.CloseKey(winreg.OpenKey(
                    root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\%s.exe" % cmd))
                return True
            except OSError:
                continue
    except Exception:
        pass
    return False


# ---- well-known folders (works even when Desktop/Documents live inside OneDrive)
_SHELL_VALUES = {"desktop": "Desktop", "documents": "Personal", "pictures": "My Pictures",
                 "videos": "My Video", "music": "My Music",
                 "downloads": "{374DE290-123F-4565-9164-39C4925E467B}"}
_DEFAULT_DIRS = {"desktop": "Desktop", "documents": "Documents", "pictures": "Pictures",
                 "videos": "Videos", "music": "Music", "downloads": "Downloads"}


def known_folder(key):
    default = Path.home() / _DEFAULT_DIRS[key]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
            p = Path(winreg.QueryValueEx(k, _SHELL_VALUES[key])[0])
            if p.exists():
                return p
    except Exception:
        pass
    return default


def screenshots_folder():
    """(path, found). Windows saves Win+PrtScn shots in Pictures\\Screenshots."""
    pics = known_folder("pictures")
    cands = [pics / "Screenshots", Path.home() / "Pictures" / "Screenshots",
             Path.home() / "OneDrive" / "Pictures" / "Screenshots",
             pics / "Assistant_Screenshots", Path.home() / "Pictures" / "Assistant_Screenshots"]
    for c in cands:
        if c.exists():
            return c, True
    return pics, False


FOLDER_ALIASES = [   # order matters: screenshots first, so "folder where I download ss" -> screenshots
    ("screenshots", r"screen\s?shots?|ss"),
    ("downloads", r"downloads?|downloaded"),
    ("desktop", r"desktop"),
    ("documents", r"documents|docs"),
    ("pictures", r"pictures|photos"),
    ("videos", r"videos"),
    ("music", r"music"),
]


def detect_folder_key(t):
    for key, pat in FOLDER_ALIASES:
        if re.search(r"\b(?:%s)\b" % pat, t):
            return key
    return None


def open_folder_for(t):
    """If the phrase asks for a well-known folder, open it and return a message; else None."""
    key = detect_folder_key(t)
    if not key:
        return None
    says_folder = re.search(r"\b(folder|directory|location|path)\b", t)
    pat = dict(FOLDER_ALIASES)[key]
    exact = re.match(r"^(?:(?:open|show|go to|kholo|khol|dikhao)\s+)?(?:my\s+|the\s+)?(?:%s)"
                     r"(?:\s+(?:kholo|khol do|dikhao|open karo))?$" % pat, t)
    if not (says_folder or exact):
        return None
    if key == "screenshots":
        path, found = screenshots_folder()
    else:
        path, found = known_folder(key), True
    try:
        os.startfile(str(path))
    except Exception as e:
        return f"Folder nahi khul paya ({path}): {e}"
    if key == "screenshots" and not found:
        return (f"Screenshots ka folder abhi bana nahi hai, isliye Pictures khol diya: {path}\n"
                "Tip: Win + PrtScn dabaoge to screenshot Pictures\\Screenshots me save hota hai.")
    return f"Opened {key} folder: {path}"


# ---- command parsing
def clean_name(name):
    name = re.sub(r"\b(?:website|site|app|application|please|pls)\b", "", name.strip().lower())
    return re.sub(r"\s+", " ", name).strip()


_BR = r"(brave|chrome|edge|firefox)"
_PROFILE_WORDS = r"(?:profile|account|with|as|for)"


def _normalize_browser_words(s):
    for alias, val in BROWSER_ALIASES.items():
        s = re.sub(r"\b%s\b" % re.escape(alias), val, s)
    return s


def split_browser(s):
    """'open youtube in chrome profile work' -> ('open youtube', 'chrome', 'work')"""
    s = _normalize_browser_words(s.strip())
    m = re.match(r"^(.*?)\s+(?:in|on|using|with)\s+%s(?:\s+%s\s+(.+))?$" % (_BR, _PROFILE_WORDS), s)
    if m:
        return m.group(1).strip(), m.group(2), (m.group(3) or "").strip() or None
    return s, None, None


def browser_choice(br, prof, ctx):
    """-> (browser, profile_folder, error). Remembers the browser/profile opened earlier in a chain."""
    browser = br or ctx.get("browser")
    if prof and browser:
        pdir, _label, err = resolve_profile(browser, prof)
        return browser, pdir, err
    pdir = ctx.get("profile") if (not br or br == ctx.get("browser")) else None
    return browser, pdir, None


_CHAIN = re.compile(r"\s*,?\s*\b(?:and then|then|after that|aur phir|phir|uske baad)\b\s*"
                    r"|\s+and\s+(?=(?:play|open|search|find)\b)")


def split_steps(text):
    """'open brave then open youtube then play X' -> ['open brave', 'play X']"""
    steps = [s.strip(" ,.") for s in _CHAIN.split(text.lower()) if s]
    steps = [s for s in steps if s and s not in ("play", "open")]
    out = []
    for i, s in enumerate(steps):
        nxt = steps[i + 1] if i + 1 < len(steps) else ""
        if re.match(r"^(?:open|launch|kholo|khol)\s+(?:youtube|yt|you tube)$", s) and nxt.startswith("play"):
            continue            # 'play' already opens YouTube, no need to open it twice
        out.append(s)
    return out


def clean_step(t):
    t = re.sub(r"^(?:(?:please|pls|can you|could you|would you|hey|ok|okay|hello|jarvis|"
               r"assistant|mujhe|mere liye|zara)\s+)+", "", t.strip().lower())
    t = re.sub(r"\s+(?:please|pls|karo|kardo|kar do)$", "", t)
    return t.strip()


def open_target(name, ctx):
    name, br = split_browser(clean_name(name))
    name = BROWSER_ALIASES.get(name, name)
    browser = br or ctx.get("browser")
    if name in BROWSERS:
        exe = find_browser(name)
        if not exe:
            return (f"{name.capitalize()} is laptop me install nahi mila, isliye kuch nahi khola. "
                    "(Dusra browser jaan-boojh ke nahi kholta.)")
        subprocess.Popen([exe])
        ctx["browser"] = name
        ctx["wait"] = True              # give the browser a moment before the next step
        return f"Opening {name}: {exe}"
    if name in SITES:
        open_url(SITES[name], browser)
        return f"Opening {name}"
    if "." in name and " " not in name:
        open_url(name if name.startswith("http") else "https://" + name, browser)
        return f"Opening {name}"
    cmd = APPS.get(name, name)
    if IS_WIN and app_exists(cmd):
        try:
            os.startfile(cmd)
            return f"Opening {name}"
        except OSError as e:
            return f"Could not open {name}: {e}"
    return (f"'{name}' naam ka app ya website nahi mila. Website ka poora naam bolo "
            "(jaise 'open amazon.in') ya 'search ...' bolo.")


def play_video(query, browser=None):
    url = None
    try:
        import pywhatkit
        url = pywhatkit.playonyt(query, open_video=False)   # only find the link, we open it ourselves
    except Exception:
        pass
    if not url or not str(url).startswith("http"):
        url = "https://www.youtube.com/results?search_query=" + quote(query)
    open_url(url, browser)
    return f"Playing {query} on YouTube"


def find_files(name, limit=20):
    name = name.lower().strip()
    home = Path.home()
    roots = [home / d for d in ("Downloads", "Desktop", "Documents", "Pictures", "Videos", "Music")]
    roots.append(home)
    found, seen, start = [], set(), time.time()
    for root in roots:
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if not d.startswith(".") and d.lower() not in ("appdata", "node_modules")]
            for f in fn:
                if name in f.lower():
                    p = os.path.join(dp, f)
                    if p not in seen:
                        seen.add(p); found.append(p)
                        if len(found) >= limit:
                            return found
            if time.time() - start > 20:
                return found
    return found


def read_gmail():
    user, pw = CFG.get("gmail_user"), CFG.get("gmail_app_password")
    if not user or not pw:
        return ("Gmail setup nahi hai. Right-click ball > 'Gmail setup' me email aur "
                "Google App Password daalo.")
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com")
        M.login(user, pw)
        M.select("INBOX")
        _, data = M.search(None, "UNSEEN")
        ids = data[0].split()[-5:]
        if not ids:
            return "Koi naya unread mail nahi hai."
        lines = []
        for i in reversed(ids):
            _, msg_data = M.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            msg = email.message_from_bytes(msg_data[0][1])
            subj, enc = decode_header(msg.get("Subject", ""))[0]
            if isinstance(subj, bytes):
                subj = subj.decode(enc or "utf-8", errors="ignore")
            lines.append(f"From: {msg.get('From','')}\n  Subject: {subj}")
        M.logout()
        return "Latest unread mails:\n" + "\n".join(lines)
    except Exception as e:
        return f"Gmail error: {e}"


@contextlib.contextmanager
def _com():
    """Windows audio/WMI calls need COM initialised in the current thread."""
    inited = False
    try:
        import comtypes
        comtypes.CoInitialize()
        inited = True
    except Exception:
        pass
    try:
        yield
    finally:
        if inited:
            try:
                import comtypes
                comtypes.CoUninitialize()
            except Exception:
                pass


def _endpoint_volume():
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    dev = AudioUtilities.GetSpeakers()
    if hasattr(dev, "EndpointVolume"):
        return dev.EndpointVolume
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


def get_volume():
    """Current volume 0-100, or None if it cannot be read."""
    try:
        with _com():
            return int(round(_endpoint_volume().GetMasterVolumeLevelScalar() * 100))
    except Exception:
        return None


def set_volume(p):
    try:
        p = max(0, min(100, int(p)))
        with _com():
            _endpoint_volume().SetMasterVolumeLevelScalar(p / 100, None)
        return f"Volume {p}%"
    except Exception as e:
        return f"Volume error: {e}"


def get_brightness():
    """Current brightness 0-100, or None if it cannot be read."""
    try:
        import screen_brightness_control as sbc
        with _com():
            v = sbc.get_brightness()
        if isinstance(v, (list, tuple)):
            v = v[0]
        return int(v)
    except Exception:
        return None


def set_brightness(p):
    try:
        import screen_brightness_control as sbc
        p = max(0, min(100, int(p)))
        with _com():
            sbc.set_brightness(p)
        return f"Brightness {p}%"
    except Exception as e:
        return f"Brightness error: {e}"


def pdf_to_jpg(pdf_path):
    import fitz  # PyMuPDF
    out = Path(pdf_path).with_suffix("")
    out.mkdir(exist_ok=True)
    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc, 1):
        page.get_pixmap(dpi=150).save(str(out / f"page_{i}.jpg"))
    return str(out)


def jpg_to_pdf(images, out_path):
    from PIL import Image
    imgs = [Image.open(p).convert("RGB") for p in images]
    imgs[0].save(out_path, save_all=True, append_images=imgs[1:])
    return out_path


def reveal(path):
    subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')


def listen_once():
    import speech_recognition as sr
    r = sr.Recognizer()
    with sr.Microphone() as src:
        r.adjust_for_ambient_noise(src, 0.5)
        audio = r.listen(src, timeout=6, phrase_time_limit=8)
    return r.recognize_google(audio, language="en-IN")


# ---------------------------------------------------------------- selected text + translate
CONSOLE_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty",
                   "VirtualConsoleClass", "Shell_TrayWnd", "Progman", "WorkerW"}


def foreground_info():
    """(hwnd, pid, window class) of the window that currently has focus."""
    if not IS_WIN:
        return 0, 0, ""
    try:
        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return 0, 0, ""
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, buf, 256)
        return hwnd, pid.value, buf.value
    except Exception:
        return 0, 0, ""


def send_ctrl(key):
    """Press Ctrl+<key> in whichever window is focused."""
    if not IS_WIN:
        return
    u = ctypes.windll.user32
    vk = ord(key.upper())
    u.keybd_event(0x11, 0, 0, 0)
    u.keybd_event(vk, 0, 0, 0)
    u.keybd_event(vk, 0, 2, 0)
    u.keybd_event(0x11, 0, 2, 0)


def save_clipboard():
    md = QApplication.clipboard().mimeData()
    if md is None:
        return None
    new = QMimeData()
    for f in md.formats():
        try:
            new.setData(f, md.data(f))
        except Exception:
            pass
    return new


def restore_clipboard(saved):
    cb = QApplication.clipboard()
    if saved is None or not saved.formats():
        cb.clear()
    else:
        cb.setMimeData(saved)


def grab_selection(panel):
    """Copy the currently selected text of the focused app, then put the old clipboard back."""
    cb = QApplication.clipboard()
    saved = save_clipboard()
    panel.suppress_until = time.time() + 2.0      # keep this temporary copy out of clipboard history
    cb.clear()
    send_ctrl("c")
    text = ""
    for _ in range(10):
        QApplication.processEvents()
        time.sleep(0.04)
        text = cb.text()
        if text.strip():
            break
    restore_clipboard(saved)
    panel.suppress_until = time.time() + 1.0
    return text.strip()


LANGS = {
    "Hindi": "hi", "English": "en", "Urdu": "ur", "Bengali": "bn", "Marathi": "mr",
    "Gujarati": "gu", "Punjabi": "pa", "Tamil": "ta", "Telugu": "te", "Kannada": "kn",
    "Malayalam": "ml", "Odia": "or", "Nepali": "ne", "Spanish": "es", "French": "fr",
    "German": "de", "Italian": "it", "Portuguese": "pt", "Russian": "ru",
    "Japanese": "ja", "Korean": "ko", "Chinese (Simplified)": "zh-CN", "Arabic": "ar",
    "Turkish": "tr", "Indonesian": "id", "Thai": "th", "Vietnamese": "vi", "Dutch": "nl",
}
LANG_NAMES = {v: k for k, v in LANGS.items()}


def _split_hard(s, limit):
    if len(quote(s)) <= limit:
        return [s]
    mid = len(s) // 2
    return _split_hard(s[:mid], limit) + _split_hard(s[mid:], limit)


def _chunks(text, limit=1800):
    out, cur = [], ""
    for piece in re.split(r"(?<=[.!?।\n])", text):
        if not piece:
            continue
        for part in _split_hard(piece, limit):
            if cur and len(quote(cur + part)) > limit:
                out.append(cur); cur = ""
            cur += part
    if cur:
        out.append(cur)
    return out


def _gtx(text, tl):
    url = "https://translate.googleapis.com/translate_a/single?" + urlencode(
        {"client": "gtx", "sl": "auto", "tl": tl, "dt": "t", "q": text})
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = "".join(seg[0] for seg in data[0] if seg and seg[0])
    detected = data[2] if len(data) > 2 and isinstance(data[2], str) else ""
    return out, detected


def _mymemory(text, tl):
    url = "https://api.mymemory.translated.net/get?" + urlencode(
        {"q": text[:450], "langpair": f"Autodetect|{tl}"})
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = data["responseData"]["translatedText"]
    return out + (" ..." if len(text) > 450 else "")


def translate_text(text, tl):
    """Returns (translated_text, detected_language_code). Needs internet."""
    detected = ""
    try:
        outs = []
        for ch in _chunks(text):
            if not ch.strip():
                outs.append(ch); continue
            res, det = _gtx(ch, tl)
            detected = detected or det
            outs.append(res + ch[len(ch.rstrip()):])
        return "".join(outs).strip(), detected
    except Exception as e1:
        try:
            return _mymemory(text, tl), detected
        except Exception:
            raise RuntimeError(str(e1))


# ---------------------------------------------------------------- translate popup
class TranslatePopup(QWidget):
    sig_result = pyqtSignal(int, str, str, str)

    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.target_hwnd = 0
        self.token = 0
        self.setWindowTitle("Translate")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(430, 470)

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.from_lbl = QLabel("From: auto")
        self.combo = QComboBox()
        for name, code in LANGS.items():
            self.combo.addItem(name, code)
        idx = self.combo.findData(CFG.get("translate_to", "hi"))
        self.combo.setCurrentIndex(idx if idx >= 0 else 0)
        top.addWidget(self.from_lbl, 1)
        top.addWidget(QLabel("To:"))
        top.addWidget(self.combo)
        lay.addLayout(top)

        lay.addWidget(QLabel("Selected text (edit kar sakte ho):"))
        self.src = QTextEdit()
        self.src.setPlaceholderText("Yahan text likho ya paste karo...")
        lay.addWidget(self.src, 1)

        lay.addWidget(QLabel("Translation:"))
        self.out = QTextEdit(); self.out.setReadOnly(True)
        lay.addWidget(self.out, 1)

        self.status = QLabel("")
        lay.addWidget(self.status)

        row = QHBoxLayout()
        self.btn_copy = QPushButton("Copy")
        self.btn_replace = QPushButton("Replace selected text")
        self.btn_close = QPushButton("Close")
        row.addWidget(self.btn_copy); row.addWidget(self.btn_replace); row.addWidget(self.btn_close)
        lay.addLayout(row)

        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(450)
        self.timer.timeout.connect(self.run_translate)
        self.src.textChanged.connect(self.timer.start)
        self.combo.currentIndexChanged.connect(self.on_lang_changed)
        self.sig_result.connect(self.on_result)
        self.btn_copy.clicked.connect(self.copy_out)
        self.btn_replace.clicked.connect(self.replace_selection)
        self.btn_close.clicked.connect(self.hide)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(e)

    def show_for(self, text, hwnd, ball):
        self.target_hwnd = hwnd or 0
        self.btn_replace.setEnabled(bool(self.target_hwnd))
        self.src.blockSignals(True); self.src.setPlainText(text); self.src.blockSignals(False)
        self.out.clear(); self.status.setText("")
        self.from_lbl.setText("From: auto")
        scr = QApplication.primaryScreen().availableGeometry()
        x = ball.x() + ball.width() + 10
        y = ball.y()
        if x + self.width() > scr.right():
            x = max(scr.left(), ball.x() - self.width() - 10)
        y = max(scr.top(), min(y, scr.bottom() - self.height()))
        self.move(x, y)
        self.show(); self.raise_(); self.activateWindow()
        if text:
            self.run_translate()
        else:
            self.src.setFocus()

    def on_lang_changed(self, _):
        CFG["translate_to"] = self.combo.currentData(); save_config(CFG)
        self.timer.start()

    def run_translate(self):
        text = self.src.toPlainText().strip()
        if not text:
            self.out.clear(); return
        code = self.combo.currentData()
        self.token += 1
        tok = self.token
        self.status.setText("Translating...")
        def work():
            try:
                res, det = translate_text(text, code)
                self.sig_result.emit(tok, res, det, "")
            except Exception as e:
                self.sig_result.emit(tok, "", "", str(e))
        threading.Thread(target=work, daemon=True).start()

    def on_result(self, tok, res, det, err):
        if tok != self.token:
            return                     # an older request, ignore
        if err:
            self.status.setText(f"Translate error: {err}  (internet check karo)")
            return
        self.out.setPlainText(res)
        self.from_lbl.setText(f"From: {LANG_NAMES.get(det, det or 'auto')} (detected)")
        self.status.setText("")

    def copy_out(self):
        text = self.out.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText("Copied.")

    def replace_selection(self):
        """Paste the translation over the text that was selected in the other app."""
        text = self.out.toPlainText()
        if not text or not self.target_hwnd:
            return
        saved = save_clipboard()
        self.panel.suppress_until = time.time() + 3.0
        QApplication.clipboard().setText(text)
        self.hide()
        if IS_WIN:
            try:
                ctypes.windll.user32.SetForegroundWindow(wintypes.HWND(self.target_hwnd))
            except Exception:
                pass
        def paste():
            send_ctrl("v")
            QTimer.singleShot(700, lambda: restore_clipboard(saved))
        QTimer.singleShot(300, paste)


# ---------------------------------------------------------------- panel
class Panel(QWidget):
    sig_log = pyqtSignal(str)
    sig_files = pyqtSignal(list)
    sig_action = pyqtSignal(str)
    sig_text = pyqtSignal(str)
    sig_quiet = pyqtSignal(str)       # log line without speaking it
    sig_sync = pyqtSignal(int, int)   # volume, brightness (-1 = leave as is)

    def __init__(self):
        super().__init__()
        self.suppress_until = 0.0     # clipboard history ignores changes until this time
        self.setWindowTitle("My Assistant")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(380, 480)
        tabs = QTabWidget()

        # --- Assistant tab
        a = QWidget(); al = QVBoxLayout(a)
        row = QHBoxLayout()
        self.input = QLineEdit(); self.input.setPlaceholderText("Type: open youtube / find resume / play song ...")
        self.input.returnPressed.connect(self.on_enter)
        mic = QPushButton("🎤"); mic.setFixedWidth(40); mic.clicked.connect(self.on_mic)
        row.addWidget(self.input); row.addWidget(mic)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(lambda it: reveal(it.text()))
        al.addLayout(row); al.addWidget(self.log, 2)
        al.addWidget(QLabel("File results (double-click = open folder):")); al.addWidget(self.results, 2)
        tabs.addTab(a, "Assistant")

        # --- Clipboard tab
        c = QWidget(); cl = QVBoxLayout(c)
        self.clip_list = QListWidget()
        self.clip_list.setIconSize(QSize(160, 90))
        self.clip_list.itemClicked.connect(self.use_clip)
        self.clip_list.itemDoubleClicked.connect(self.save_clip_image)
        clear = QPushButton("Clear history"); clear.clicked.connect(self.clip_list.clear)
        hint = QLabel("Click = dobara copy  |  Screenshot pe double-click = file me save")
        hint.setWordWrap(True)
        cl.addWidget(hint); cl.addWidget(self.clip_list); cl.addWidget(clear)
        tabs.addTab(c, "Clipboard")

        # --- Controls tab
        t = QWidget(); tl = QVBoxLayout(t)
        self.vol_lbl = QLabel("🔊 Speaker volume: 50%")
        self.vol = QSlider(Qt.Orientation.Horizontal); self.vol.setRange(0, 100); self.vol.setValue(50)
        self.bri_lbl = QLabel("💡 Screen brightness: 70%")
        self.bri = QSlider(Qt.Orientation.Horizontal); self.bri.setRange(0, 100); self.bri.setValue(70)

        # change is applied ~0.3s after the slider stops moving (works for drag, click, arrow keys)
        self.vol_timer = QTimer(self); self.vol_timer.setSingleShot(True); self.vol_timer.setInterval(300)
        self.vol_timer.timeout.connect(lambda: self.apply_async(set_volume, self.vol.value()))
        self.bri_timer = QTimer(self); self.bri_timer.setSingleShot(True); self.bri_timer.setInterval(400)
        self.bri_timer.timeout.connect(lambda: self.apply_async(set_brightness, self.bri.value()))
        self.vol.valueChanged.connect(self.on_vol_change)
        self.bri.valueChanged.connect(self.on_bri_change)

        b1 = QPushButton("PDF ➜ JPG"); b1.clicked.connect(lambda: self.do_action("pdf2jpg"))
        b2 = QPushButton("JPG ➜ PDF"); b2.clicked.connect(lambda: self.do_action("jpg2pdf"))
        tl.addWidget(self.vol_lbl); tl.addWidget(self.vol)
        tl.addWidget(self.bri_lbl); tl.addWidget(self.bri)
        tl.addWidget(b1); tl.addWidget(b2); tl.addStretch()
        tabs.addTab(t, "Controls")

        lay = QVBoxLayout(self); lay.addWidget(tabs)

        self.sig_log.connect(self.say)
        self.sig_quiet.connect(self.log.append)
        self.sig_sync.connect(self.on_sync)
        self.sig_files.connect(self.show_files)
        self.sig_action.connect(self.do_action)
        self.sig_text.connect(self.input.setText)

        cb = QApplication.clipboard()
        cb.dataChanged.connect(self.on_clip)

        QTimer.singleShot(600, self.sync_sliders)   # read real volume/brightness at start

    # --- sliders
    def on_vol_change(self, v):
        self.vol_lbl.setText(f"🔊 Speaker volume: {v}%")
        self.vol_timer.start()

    def on_bri_change(self, v):
        self.bri_lbl.setText(f"💡 Screen brightness: {v}%")
        self.bri_timer.start()

    def apply_async(self, fn, value):
        def run():
            self.sig_quiet.emit(fn(value))
        threading.Thread(target=run, daemon=True).start()

    def sync_sliders(self):
        def run():
            v, b = get_volume(), get_brightness()
            self.sig_sync.emit(-1 if v is None else v, -1 if b is None else b)
        threading.Thread(target=run, daemon=True).start()

    def on_sync(self, v, b):
        if v >= 0:
            self.vol.blockSignals(True); self.vol.setValue(v); self.vol.blockSignals(False)
        if b >= 0:
            self.bri.blockSignals(True); self.bri.setValue(b); self.bri.blockSignals(False)
        self.vol_lbl.setText(f"🔊 Speaker volume: {self.vol.value()}%")
        self.bri_lbl.setText(f"💡 Screen brightness: {self.bri.value()}%")

    # --- clipboard
    def add_clip_item(self, kind, key, value, label, icon=None):
        for i in range(self.clip_list.count()):
            d = self.clip_list.item(i).data(Qt.ItemDataRole.UserRole)
            if d and d["key"] == key:
                self.clip_list.takeItem(i); break
        item = QListWidgetItem(label)
        if icon is not None:
            item.setIcon(icon)
        item.setData(Qt.ItemDataRole.UserRole, {"kind": kind, "key": key, "value": value})
        self.clip_list.insertItem(0, item)
        while self.clip_list.count() > 30:
            self.clip_list.takeItem(self.clip_list.count() - 1)

    def on_clip(self):
        if time.time() < self.suppress_until:
            return
        try:
            cb = QApplication.clipboard()
            md = cb.mimeData()
            if md is None:
                return
            if md.hasText() and md.text().strip():
                txt = md.text().strip()
                self.add_clip_item("text", "t:" + txt, txt, txt[:120].replace("\n", " ↵ "))
            elif md.hasImage():
                img = cb.image()
                if img.isNull():
                    return
                data = QByteArray()
                buf = QBuffer(data); buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img.save(buf, "BMP"); buf.close()
                key = "i:" + hashlib.md5(bytes(data)).hexdigest()
                thumb = QPixmap.fromImage(img).scaled(
                    160, 90, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                label = f"🖼 Screenshot {img.width()}x{img.height()}  •  {datetime.now():%H:%M:%S}"
                self.add_clip_item("image", key, img, label, QIcon(thumb))
        except Exception as e:
            self.log.append(f"Clipboard error: {e}")

    def use_clip(self, item):
        d = item.data(Qt.ItemDataRole.UserRole)
        if not d:
            return
        if d["kind"] == "text":
            QApplication.clipboard().setText(d["value"])
        else:
            QApplication.clipboard().setImage(d["value"])
        self.say("Copied. Ab Ctrl+V karo.")

    def save_clip_image(self, item):
        d = item.data(Qt.ItemDataRole.UserRole)
        if not d or d["kind"] != "image":
            return
        folder = Path.home() / "Pictures" / "Assistant_Screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"shot_{datetime.now():%Y%m%d_%H%M%S}.png"
        if d["value"].save(str(path), "PNG"):
            self.say(f"Screenshot saved: {path}")
            reveal(str(path))
        else:
            self.say("Screenshot save nahi ho paya.")

    # --- UI helpers
    def say(self, text):
        self.log.append(text); speak(text.split("\n")[0])

    def show_files(self, files):
        self.results.clear()
        self.results.addItems(files)
        self.say(f"{len(files)} file(s) mili." if files else "Koi file nahi mili.")

    def toggle(self, ball):
        if self.isVisible():
            self.hide()
        else:
            self.move(ball.x() + ball.width() + 10, max(0, ball.y()))
            self.show(); self.raise_(); self.input.setFocus()

    # --- input
    def on_enter(self):
        text = self.input.text().strip()
        if text:
            self.input.clear(); self.log.append(f"> {text}")
            threading.Thread(target=self.handle, args=(text,), daemon=True).start()

    def on_mic(self):
        self.log.append("🎤 Listening...")
        def run():
            try:
                text = listen_once()
                self.sig_log.emit(f"> {text}")
                self.handle(text)
            except Exception as e:
                self.sig_log.emit(f"Voice error: {e}")
        threading.Thread(target=run, daemon=True).start()

    # --- command brain (runs in thread; talk to UI via signals)
    def handle(self, text):
        """Runs one or several commands: 'open brave then open youtube then play <song>'."""
        steps = split_steps(text)
        if not steps:
            return self.sig_log.emit("Kuch samajh nahi aaya, dobara bolo.")
        ctx = {}
        for i, step in enumerate(steps):
            self.run_step(step, ctx)
            if ctx.pop("wait", False) and i < len(steps) - 1:
                time.sleep(2.5)

    def run_step(self, t, ctx):
        log = self.sig_log.emit
        t = clean_step(t)

        msg = open_folder_for(t)                       # 'open downloads folder', 'folder where I download ss'
        if msg:
            return log(msg)

        m = re.match(r"^play\s+(.+)$", t)
        if m:
            q, br = split_browser(m.group(1))
            q = re.sub(r"\s+on\s+youtube$", "", q)
            return log(play_video(q, br or ctx.get("browser")))

        m = re.match(r"^(?:open|launch|kholo|khol)\s+(.+)$", t) or \
            re.match(r"^(.+?)\s+(?:kholo|khol do|open karo|chalu karo)$", t)
        if m:
            return log(open_target(m.group(1), ctx))

        m = re.match(r"^(?:find|dhundo|dhoondo|locate)\s+(?:file\s+)?(.+)$", t)
        if m:
            q = re.sub(r"\s+(?:in|from)\s+(?:my\s+)?(?:downloads?|desktop|documents|pictures)$", "", m.group(1))
            log(f"Searching '{q}' ...")
            return self.sig_files.emit(find_files(q))

        if re.search(r"\b(?:read|check|show|any|new|unread)\b.*\b(?:mails?|emails?|gmail)\b", t) \
                or t in ("mail", "mails", "email", "emails", "gmail"):
            return log(read_gmail())

        m = re.search(r"volume.*?(\d+)", t)
        if m:
            p = max(0, min(100, int(m.group(1))))
            self.sig_sync.emit(p, -1)
            return log(set_volume(p))
        m = re.search(r"brightness.*?(\d+)", t)
        if m:
            p = max(0, min(100, int(m.group(1))))
            self.sig_sync.emit(-1, p)
            return log(set_brightness(p))

        if "pdf to jpg" in t or "pdf to image" in t:
            return self.sig_action.emit("pdf2jpg")
        if "jpg to pdf" in t or "image to pdf" in t:
            return self.sig_action.emit("jpg2pdf")

        m = re.match(r"^(?:search|google)\s+(?:for\s+)?(.+)$", t)
        if m:
            q, br = split_browser(m.group(1))
            open_url("https://www.google.com/search?q=" + quote(q), br or ctx.get("browser"))
            return log(f"Google search: {q}")

        log(f"Samajh nahi aaya: '{t}'\n"
            "Try: open youtube | play <song> | open downloads folder | open screenshots folder | "
            "find <file> | search <text>")

    # --- actions needing dialogs (main thread)
    def do_action(self, kind):
        try:
            if kind == "pdf2jpg":
                p, _ = QFileDialog.getOpenFileName(self, "Select PDF", str(Path.home()), "PDF (*.pdf)")
                if p:
                    self.say(f"Saved JPGs in: {pdf_to_jpg(p)}")
            elif kind == "jpg2pdf":
                ps, _ = QFileDialog.getOpenFileNames(self, "Select images", str(Path.home()),
                                                     "Images (*.jpg *.jpeg *.png)")
                if ps:
                    out, _ = QFileDialog.getSaveFileName(self, "Save PDF as", str(Path.home() / "output.pdf"), "PDF (*.pdf)")
                    if out:
                        self.say(f"PDF saved: {jpg_to_pdf(ps, out)}")
        except Exception as e:
            self.say(f"Convert error: {e}")


# ---------------------------------------------------------------- ball
SHAPES = {"circle": "Circle", "rounded": "Rounded square", "hexagon": "Hexagon",
          "diamond": "Diamond", "star": "Star"}


def shape_path(shape, r):
    """Outline of the ball inside rectangle r (QRectF)."""
    path = QPainterPath()
    cx, cy, R = r.center().x(), r.center().y(), r.width() / 2
    if shape == "rounded":
        path.addRoundedRect(r, r.width() * 0.28, r.height() * 0.28)
    elif shape == "hexagon":
        pts = [QPointF(cx + R * math.cos(math.radians(-90 + 60 * i)),
                       cy + R * math.sin(math.radians(-90 + 60 * i))) for i in range(6)]
        path.addPolygon(QPolygonF(pts)); path.closeSubpath()
    elif shape == "diamond":
        pts = [QPointF(cx, r.top()), QPointF(r.right(), cy), QPointF(cx, r.bottom()), QPointF(r.left(), cy)]
        path.addPolygon(QPolygonF(pts)); path.closeSubpath()
    elif shape == "star":
        pts = []
        for i in range(10):
            rad = R if i % 2 == 0 else R * 0.45
            ang = math.radians(-90 + 36 * i)
            pts.append(QPointF(cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        path.addPolygon(QPolygonF(pts)); path.closeSubpath()
    else:
        path.addEllipse(r)
    return path


class Ball(QWidget):
    def __init__(self, panel, popup):
        super().__init__()
        self.panel = panel
        self.popup = popup
        # WindowDoesNotAcceptFocus: clicking the ball does NOT steal focus from the app
        # where you selected text (needed for the translate feature).
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.photo_pix = None
        self.avatar_pix = None
        self._av_cache = (0, None)
        self._moved = False
        self.phase = 0.0
        self.apply_config()
        self.anim = QTimer(self)
        self.anim.timeout.connect(self.tick)
        self.anim.start(40)

    # --- geometry / config
    def metrics(self):
        size = int(CFG["size"])
        pad = max(8, int(size * 0.14))
        box = int(size * 1.35) if self.avatar_pix else size
        return size, pad, box

    def apply_config(self):
        self.avatar_pix = None
        av = CFG.get("avatar", "")
        if av:
            p = Path(av) if os.path.isabs(av) else AVATAR_DIR / av
            if p.exists():
                pm = QPixmap(str(p))
                if not pm.isNull():
                    self.avatar_pix = pm
        img = CFG.get("image", "")
        self.photo_pix = QPixmap(img) if img and os.path.exists(img) else None
        self._av_cache = (0, None)
        _, pad, box = self.metrics()
        side = box + 2 * pad
        self.resize(side, side)
        self.move(int(CFG["x"]), int(CFG["y"]))
        self.update()

    def tick(self):
        self.phase += 0.12
        self.update()

    def avatar_scaled(self, box):
        if self._av_cache[0] != box or self._av_cache[1] is None:
            sp = self.avatar_pix.scaled(box, box, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
            self._av_cache = (box, sp)
        return self._av_cache[1]

    # --- drawing
    def paintEvent(self, _):
        size, pad, box = self.metrics()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bob = math.sin(self.phase) * pad * 0.35          # gentle floating motion
        cx = self.width() / 2

        # soft ground shadow (shrinks a little when the ball floats up)
        sw = box * (0.62 + 0.05 * math.sin(self.phase))
        sh = pad * 0.55
        sy = pad + box + pad * 0.15
        p.save()
        p.translate(cx, sy)
        p.scale(1, sh / sw)
        g = QRadialGradient(QPointF(0, 0), sw / 2)
        g.setColorAt(0, QColor(0, 0, 0, 95)); g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(0, 0), sw / 2, sw / 2)
        p.restore()

        r = QRectF(pad, pad + bob, box, box)

        # ---- character avatar (no ball)
        if self.avatar_pix:
            sp = self.avatar_scaled(box)
            x = r.x() + (box - sp.width()) / 2
            y = r.y() + box - sp.height()
            p.drawPixmap(int(x), int(y), sp)
            return

        # ---- ball in chosen shape
        path = shape_path(CFG.get("shape", "circle"), r)
        base = QColor(CFG["color"])
        d3 = bool(CFG.get("style3d", True))
        if self.photo_pix and not self.photo_pix.isNull():
            p.save()
            p.setClipPath(path)
            sc = self.photo_pix.scaled(r.size().toSize(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(int(r.x() + (r.width() - sc.width()) / 2),
                         int(r.y() + (r.height() - sc.height()) / 2), sc)
            p.restore()
        else:
            if d3:
                grad = QRadialGradient(QPointF(r.x() + r.width() * 0.35, r.y() + r.height() * 0.30),
                                       r.width() * 0.9)
                grad.setColorAt(0.0, base.lighter(190))
                grad.setColorAt(0.45, base)
                grad.setColorAt(1.0, base.darker(210))
                p.setBrush(QBrush(grad))
            else:
                p.setBrush(QBrush(base))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(path)

        if d3:
            # glossy highlight on the upper part
            p.save()
            p.setClipPath(path)
            hl = QLinearGradient(QPointF(r.x(), r.y()), QPointF(r.x(), r.y() + r.height() * 0.55))
            hl.setColorAt(0, QColor(255, 255, 255, 130)); hl.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(QBrush(hl)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(r.x() + r.width() * 0.12, r.y() + r.height() * 0.04,
                                 r.width() * 0.76, r.height() * 0.5))
            p.restore()

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 170), 2))
        p.drawPath(path)

    # --- mouse
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = e.globalPosition().toPoint()
            self._off = self._start - self.frameGeometry().topLeft()
            self._moved = False

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            pos = e.globalPosition().toPoint()
            if (pos - self._start).manhattanLength() > 4:
                self._moved = True
            if self._moved:
                self.move(pos - self._off)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._moved:
            CFG["x"], CFG["y"] = self.x(), self.y(); save_config(CFG)
        else:
            self.on_click()

    def on_click(self):
        """Text selected in another app -> translate popup. Otherwise -> assistant panel."""
        hwnd, pid, cls = foreground_info()
        if IS_WIN and hwnd and pid != os.getpid() and cls not in CONSOLE_CLASSES:
            text = grab_selection(self.panel)
            if text:
                self.popup.show_for(text, hwnd, self)
                return
        self.panel.toggle(self)

    # --- right-click menu
    def contextMenuEvent(self, e):
        m = QMenu(self)
        self._add(m, "🧍 Change avatar...", self.pick_avatar)

        sm = m.addMenu("⬡ Shape")
        for key, label in SHAPES.items():
            a = QAction(label, self)
            a.setCheckable(True); a.setChecked(CFG.get("shape", "circle") == key)
            a.triggered.connect(lambda _=False, k=key: self.set_shape(k))
            sm.addAction(a)

        a3 = QAction("✨ 3D effect", self)
        a3.setCheckable(True); a3.setChecked(bool(CFG.get("style3d", True)))
        a3.triggered.connect(self.toggle_3d)
        m.addAction(a3)

        self._add(m, "🎨 Change colour", self.pick_color)
        self._add(m, "↔ Change size", self.pick_size)
        self._add(m, "🖼 Photo inside ball...", self.pick_photo)
        self._add(m, "Remove photo", self.clear_photo)
        m.addSeparator()
        self._add(m, "🌐 Translate (type / paste text)", lambda: self.popup.show_for("", 0, self))
        self._add(m, "✉ Gmail setup", self.gmail_setup)
        self._add(m, "🔈 Toggle voice reply", self.toggle_speak)
        m.addSeparator()
        q = QAction("Quit", self); q.triggered.connect(QApplication.quit); m.addAction(q)
        m.exec(e.globalPos())

    def _add(self, menu, label, fn):
        a = QAction(label, self)
        a.triggered.connect(lambda _=False: fn())
        menu.addAction(a)

    def set_shape(self, k):
        CFG["shape"] = k; CFG["avatar"] = ""; save_config(CFG); self.apply_config()

    def toggle_3d(self):
        CFG["style3d"] = not CFG.get("style3d", True); save_config(CFG); self.update()

    def pick_color(self):
        c = QColorDialog.getColor(QColor(CFG["color"]), self)
        if c.isValid():
            CFG["color"] = c.name(); CFG["avatar"] = ""; save_config(CFG); self.apply_config()

    def pick_size(self):
        v, ok = QInputDialog.getInt(self, "Size", "Size (40-250):", int(CFG["size"]), 40, 250)
        if ok:
            CFG["size"] = v; save_config(CFG); self.apply_config()

    def pick_photo(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose image", str(Path.home()), "Images (*.png *.jpg *.jpeg)")
        if p:
            CFG["image"] = p; CFG["avatar"] = ""; save_config(CFG); self.apply_config()

    def clear_photo(self):
        CFG["image"] = ""; save_config(CFG); self.apply_config()

    def pick_avatar(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Choose avatar")
        dlg.resize(580, 460)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Ek character chuno (click karo):"))
        lst = QListWidget()
        lst.setViewMode(QListView.ViewMode.IconMode)
        lst.setIconSize(QSize(110, 110))
        lst.setResizeMode(QListView.ResizeMode.Adjust)
        lst.setMovement(QListView.Movement.Static)
        lst.setSpacing(10)

        it = QListWidgetItem("Plain ball")
        it.setData(Qt.ItemDataRole.UserRole, ("none", ""))
        lst.addItem(it)
        if AVATAR_DIR.exists():
            for f in sorted(AVATAR_DIR.glob("*.png")):
                it = QListWidgetItem(QIcon(QPixmap(str(f))), f.stem.replace("avatar", "Avatar "))
                it.setData(Qt.ItemDataRole.UserRole, ("avatar", f.name))
                lst.addItem(it)
        it = QListWidgetItem("My own image...")
        it.setData(Qt.ItemDataRole.UserRole, ("browse", ""))
        lst.addItem(it)

        chosen = {}
        def on_pick(item):
            chosen["v"] = item.data(Qt.ItemDataRole.UserRole)
            dlg.accept()
        lst.itemClicked.connect(on_pick)
        lay.addWidget(lst)
        lay.addWidget(QLabel("Tip: apni image ke liye transparent background wali PNG best rehti hai."))

        if not dlg.exec() or "v" not in chosen:
            return
        kind, val = chosen["v"]
        if kind == "none":
            CFG["avatar"] = ""
        elif kind == "avatar":
            CFG["avatar"] = val
        else:
            p, _ = QFileDialog.getOpenFileName(self, "Choose avatar image", str(Path.home()),
                                               "Images (*.png *.jpg *.jpeg *.webp)")
            if not p:
                return
            CFG["avatar"] = p
        save_config(CFG)
        self.apply_config()

    def gmail_setup(self):
        u, ok = QInputDialog.getText(self, "Gmail", "Gmail address:", text=CFG["gmail_user"])
        if not ok: return
        pw, ok = QInputDialog.getText(self, "Gmail", "Google App Password (16 chars):",
                                      QLineEdit.EchoMode.Password)
        if ok:
            CFG["gmail_user"], CFG["gmail_app_password"] = u, pw.replace(" ", ""); save_config(CFG)

    def toggle_speak(self):
        CFG["speak"] = not CFG.get("speak", True); save_config(CFG)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    panel = Panel()
    popup = TranslatePopup(panel)
    ball = Ball(panel, popup)
    ball.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
