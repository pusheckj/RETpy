# How to Run This — Beginner's Guide

This guide assumes you've never used a terminal before. If you're comfortable with the command line, see the [main README](README.md) instead.

There are two parts to do once: **install Python**, then **install this app's ingredients**. After that, running it is just one command (or double-click, on Windows).

---

## If you have a Windows PC

### Step 1 — Install Python (one-time)
1. Go to [python.org/downloads](https://www.python.org/downloads/) and click the big "Download Python" button.
2. Open the downloaded file to install it.
3. **Important:** on the first install screen, there's a small checkbox at the bottom that says **"Add Python to PATH"** — check that box before clicking Install. Easy to miss, but if you skip it, nothing else below will work.

### Step 2 — Get the app files
1. Find the ZIP file you were given and double-click it to unzip it. You'll get a regular folder.
2. Put that folder somewhere easy to find, like your Desktop.

### Step 3 — Open the black typing window
Click the Start menu, type `cmd`, and press Enter. A plain black window will pop up — that's normal, not an error.

### Step 4 — Tell it where the folder is
Type `cd ` (with a space after it), then drag the unzipped folder from your Desktop into the black window, and press Enter.

### Step 5 — Install the app's ingredients (one-time)
Copy and paste each line below, pressing Enter after each, and wait for it to finish before the next:
```
pip install -r requirements.txt
pip install -r ui\requirements-ui.txt
```

### Step 6 — Run it
```
ui\run.bat
```
Your web browser should open on its own with the app in it. If it doesn't, open your browser and go to `http://localhost:8501`.

### Step 7 — When you're done
Close the browser tab, then close the black window.

---

## If you have a Mac

### Step 1 — Install Python (one-time)
Go to [python.org/downloads](https://www.python.org/downloads/), download the macOS installer, and open it to install.

### Step 2 — Get the app files
Double-click the ZIP file to unzip it.

### Step 3 — Open Terminal
Press `Cmd+Space`, type `Terminal`, press Enter. A window with text will open — that's normal.

### Step 4 — Tell it where the folder is
Type `cd ` (with a space), drag the unzipped folder into the Terminal window, and press Enter.

### Step 5 — Install the app's ingredients (one-time)
```
pip3 install -r requirements.txt
pip3 install -r ui/requirements-ui.txt
```

### Step 6 — Run it
```
bash ui/run.sh
```
Your browser will open automatically with the app. If it doesn't, open your browser and go to `http://localhost:8501`.

### Step 7 — When you're done
Close the browser tab, then close the Terminal window.

---

## Next time you want to run it

You only need to do Steps 1, 2, and 5 once. After that, just repeat Steps 3–4 and 6 (open the terminal/command window, `cd` into the folder, run it).

## Something went wrong?

- **"python is not recognized" / "command not found"** — Python didn't get added to your system's PATH. Reinstall Python and make sure to check "Add Python to PATH" (Windows) or just try `python3` instead of `python` (Mac).
- **"pip is not recognized"** — same fix as above; reinstall Python with the PATH option checked.
- **The browser doesn't open automatically** — just open any browser yourself and go to `http://localhost:8501`.
- **Anything else** — see the more detailed [`ui/README_UI.md`](ui/README_UI.md), or the [main README](README.md).
