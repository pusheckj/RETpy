# Hosting the app (invite-only, Streamlit Community Cloud)

Free hosting for a small group of people you invite by email. About 15 minutes
the first time; after that, every `git push` redeploys the app.

## What visitors get

- A first screen that asks what they want: the simple **money check-up**
  (savings rate, emergency fund, which debt to pay first, where the next
  dollar goes) or the **retirement planner**. A *Money check-up | Retirement
  planner* switch at the top right of every page flips between them; each
  keeps its own answers.
- The retirement planner opens with a short guided setup (10 screens, a few
  questions each, with a "how to answer" line under every question). Anyone
  coming from the check-up starts with those answers filled in. *Skip for now*
  goes straight to the planner; a banner offers to finish later.
- Their inputs live in their own browser session. *Remember me on this device*
  keeps them (and how far they got in the setup) in that browser only, so
  they're back after a reload or an app update; *Settings → Save* downloads
  them to their computer.
- A Spending tab that analyses statements **they upload** (CSV, PDF, optional
  rules JSON). Files are parsed in memory for that session only and never
  saved. The hosted app never reads the server's folders. *Use my actual
  spending* copies those averages into the plan's monthly expenses.
- Runs take turns: if two people start a fresh simulation at once, the second
  waits for the first (usually a few seconds; longer on the free tier).

Your own profile is **not** in the repository. It lives on your Mac at
`~/.config/retirement-sim/my_profile.json` (or wherever `RETIREMENT_SIM_PROFILE`
points) and only appears in the app you run locally.

## 1. Push the code to GitHub (one time)

Run this from Terminal on your own machine (Claude Code's network sandbox
blocks github.com). Make the repository **private** on GitHub first
(Settings → General → Danger Zone → Change visibility) unless you want the
code public.

```bash
cd "<package folder>"            # the folder containing ui/, retirement_sim/, tests/
gh auth login --hostname github.com   # or set up an SSH key / personal access token
git push -u origin main
```

If GitHub created a README or license when you made the repo, the push is
rejected. Merge GitHub's commit once, then push:

```bash
git pull origin main --allow-unrelated-histories --no-edit
git push -u origin main
```

## 2. Deploy on Streamlit Community Cloud

1. Go to <https://share.streamlit.io> and sign in with GitHub. Grant access to
   private repositories if you made the repo private.
2. **Create app** and choose to deploy from a GitHub repository:
   - Repository: `pusheckj/RETpy`, Branch: `main`
   - Main file path: `ui/app.py`
3. **Advanced settings**
   - Python version: **3.12**
   - Secrets: paste the contents of `.streamlit/secrets.toml.example`:
     ```toml
     RETIREMENT_SIM_HOSTED = "1"
     RETIREMENT_SIM_MAX_WORKERS = "2"
     ```
4. **Deploy.** The first build installs `ui/requirements.txt` (a few minutes).

## 3. Make it invite-only

App menu (⋮) → **Settings → Sharing** → *Who can view this app* →
**Only specific people** → add each person's email. Viewers sign in with that
email. If the app is ever set to public, anyone with the link can use it.

## 4. Updating

Commit and `git push`; the app redeploys automatically. Your local app
(`bash ui/run.sh`) keeps working exactly as before, including your profile and
your statements folder.

## Settings

| Variable | Default | Effect |
|---|---|---|
| `RETIREMENT_SIM_HOSTED` | off locally; on automatically on Streamlit Cloud | Spending tab takes uploads only; no server folders; 500 simulations by default |
| `RETIREMENT_SIM_MAX_WORKERS` | 8 locally, 2 hosted | Cap on parallel simulation processes (`1` = never fork) |
| `RETIREMENT_SIM_PROFILE` | `~/.config/retirement-sim/my_profile.json` | Your private profile (local only) |
| `SPENDING_DATA_DIR` | from `~/.config/retirement-sim/spending.json` | Your statements folder (local only; ignored when hosted) |

## Good to know

- **Sleeping:** free apps sleep after a period without visitors; the first
  visit afterwards wakes it in about 30 seconds.
- **Speed:** the free tier has little CPU. 500 simulations is the hosted
  default; visitors can pick more and wait longer.
- **Streamlit version:** `ui/requirements.txt` pins Streamlit because the
  theme's CSS targets its page structure. When you upgrade, check the layout
  locally first.
- **Results cache:** when hosted, recent simulation results are cached in
  memory only (never written to disk), keyed by the numbers entered, so repeat
  runs are instant. It is gone whenever the app restarts or redeploys.
