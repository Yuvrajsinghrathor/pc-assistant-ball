# MyAssistant

**A floating desktop assistant ball for Windows.** Click the ball, type or speak a command, and it opens sites, plays songs, finds files, reads your mail, converts PDFs, keeps a clipboard history (with screenshots) and translates any text you select.

Built with Python and PyQt6.

## Features

| | |
|---|---|
| **Floating ball** | Always on top, draggable, 3D glossy look with a gentle floating animation. |
| **Customisable** | Size, colour, 5 shapes (circle, rounded square, hexagon, diamond, star), a photo inside the ball, or a full character avatar. Settings are remembered. |
| **Text and voice commands** | Type in the panel or press the mic button. Chain steps: `open brave then open youtube then play <song>`. |
| **Open and play** | Websites, apps, YouTube songs. Choose the browser (Brave, Chrome, Edge, Firefox) and even a specific Chrome profile (Google account). |
| **Open folders** | "open downloads folder", "open screenshots folder", desktop, documents, pictures, and so on (works with OneDrive-redirected folders). |
| **Find files** | Say a file name and it lists matches. Double-click a result to open its folder. |
| **Clipboard history** | Keeps the last 30 copied texts **and screenshots**. Click an item to copy it again. Double-click a screenshot to save it as PNG. |
| **Translate selected text** | Select text in any app, click the ball, pick a language (28 available). Copy the result, or replace the selected text with it. |
| **PDF ⇄ JPG** | Convert every PDF page to JPG, or combine images into one PDF. |
| **Volume and brightness** | Sliders with live percent, or say `volume 40`. |
| **Gmail** | Shows your latest unread mails (needs a Google App Password). |

## Download (no Python needed)

1. Go to the [**Releases**](../../releases) page and download `MyAssistant.zip`.
2. Unzip it anywhere (do not run it from inside the zip).
3. Double-click `MyAssistant.exe`.

> **Windows protected your PC?** The app is not code-signed, so Windows warns about it. Click **More info → Run anyway**.

## Run from source

Requires **Windows** and **Python 3.11 or 3.12** (tick *Add Python to PATH* when installing).

```bat
git clone https://github.com/<your-username>/MyAssistant.git
cd MyAssistant
python -m pip install -r requirements.txt
python assistant.py
```

If `PyAudio` fails to install (only needed for the microphone):

```bat
python -m pip install pipwin
python -m pipwin install pyaudio
```

The app still works without it. Only the mic button will not.

## Using it

- **Left click** the ball: open the panel (Assistant, Clipboard and Controls tabs).
- **Drag** the ball to move it. The position is saved.
- **Right click** the ball: change avatar, shape, 3D effect, colour, size, photo, Gmail setup, voice reply, Quit.
- **Select text in any app, then left click the ball**: translate popup.

### Example commands

| Say or type | What happens |
|---|---|
| `open youtube`, `open notepad` | Opens the site or app |
| `play arijit singh songs` | Plays it on YouTube |
| `open brave then open youtube then play <song>` | Runs the steps in order, in the same browser |
| `open chrome profile work` | Opens Chrome with the chosen profile |
| `list chrome profiles` | Shows your Chrome profiles and their emails |
| `open downloads folder`, `open screenshots folder` | Opens that folder in Explorer |
| `find resume` | Searches Downloads, Desktop, Documents, Pictures, Videos and Music |
| `read my mail` | Shows the latest unread emails |
| `volume 40`, `brightness 70` | Sets it and moves the slider |
| `pdf to jpg`, `jpg to pdf` | Opens the file picker and converts |
| `search python tutorial` | Google search |

## Custom avatars

Create an `avatars` folder next to `assistant.py` and put transparent-background **PNG** files in it. They appear in **right click → Change avatar...**. You can also pick any image from your computer with **My own image...**.

No avatars are bundled with this repository.

## Gmail setup

Gmail does not accept your normal password here.

1. Turn on 2-Step Verification in your Google Account.
2. Create an **App Password** (Google Account → Security → App passwords).
3. Right click the ball → **Gmail setup** and enter your address and the 16-character app password.

> The app password is stored as **plain text** in `~/.pc_assistant.json` on your own computer. Do not share or commit that file.

## Build the .exe yourself

Double-click `build.bat`. It installs the libraries, runs PyInstaller and creates:

- `dist\MyAssistant\MyAssistant.exe`: the app
- `dist\MyAssistant.zip`: a zip you can share

Upload the zip to the **Releases** page of your repository so others can download it.

## Project structure

```
MyAssistant/
├── assistant.py        # the whole app (ball, panel, commands, translate, clipboard)
├── requirements.txt    # Python libraries
├── build.bat           # builds the .exe with PyInstaller
├── README_USERS.txt    # short guide placed inside the downloadable zip
└── avatars/            # optional: your own transparent PNG characters
```

## Tech stack

PyQt6 · SpeechRecognition + PyAudio · pyttsx3 · pywhatkit · PyMuPDF · Pillow · pycaw + comtypes · screen-brightness-control · PyInstaller

## Known limitations

- **Windows only.** Volume, brightness, folder detection, browser launch and translate-on-selection use Windows APIs.
- Translation and voice recognition **need an internet connection**. Translation uses a public Google Translate web endpoint and may stop working if Google changes it.
- Commands are matched with simple rules, not an AI model, so phrases outside the examples above may not be understood.
- Brightness control works on laptop screens. Many external monitors do not support it.
- "Replace selected text" can paste at the cursor in apps that lose their selection when focus changes.
- Translate-on-selection does not work when the focused window is a terminal such as Command Prompt.

## Roadmap

- [ ] AI-powered free-form commands
- [ ] GIF or real 3D avatars
- [ ] Start with Windows, tray icon and hotkey
- [ ] Wake word for hands-free voice

## License

MIT. See [LICENSE](LICENSE).
