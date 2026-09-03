# Making your edits stick

Without this, edits made in the app live only in your browser session and vanish
when the app restarts. Streamlit Cloud rebuilds the app from GitHub each time, so
anything the running copy wrote to its own disk is thrown away.

With this, saving in the editor commits straight to your repo. The app redeploys
and the change is live. Nothing to download, nothing to push by hand.

Takes about five minutes, once.

---

## 1. Create a GitHub token

1. GitHub → your avatar → **Settings**
2. Bottom of the left menu → **Developer settings**
3. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
4. Fill in:
   - **Token name:** `yellow-card-dashboard`
   - **Expiration:** 90 days (or longer — you'll need to replace it when it expires)
   - **Repository access:** *Only select repositories* → pick the repo holding this app
   - **Permissions** → *Repository permissions* → find **Contents** → set to **Read and write**
5. **Generate token**, then copy it. GitHub shows it once.

Only that one repo, only Contents. Nothing else.

## 2. Add it to Streamlit

1. share.streamlit.io → your app → **⋮** → **Settings** → **Secrets**
2. Paste this, filling in your own values:

```toml
editor_password = "pick-something-only-you-know"

[github]
token  = "github_pat_..."
repo   = "your-username/your-repo-name"
path   = "MASTER_dataset.json"
branch = "main"
```

3. **Save.** The app restarts on its own.

`repo` is exactly what's in the GitHub URL after `github.com/` — for
`github.com/Okaks/yellow-card-scoring` it's `Okaks/yellow-card-scoring`.

## 3. Check it worked

Open the app, go to **Edit data**, enter your password. The tab should say saves
commit to GitHub. Change something small, save, and look at your repo — there
should be a fresh commit.

---

## Running locally

Same file, different location: create `.streamlit/secrets.toml` in the project
folder and put the same contents in it.

**Add `.streamlit/secrets.toml` to `.gitignore`.** A token committed to a public
repo gets found and used by scrapers within minutes.

## If you skip this

The app still works. The editor falls back to session-only, and the Download
button gives you the updated file to commit yourself. Everything else is unaffected.

## The password

Separate from the token, and it does a different job. Without it, anyone opening
your demo could edit or delete your data. With it, they can explore everything —
all three views, the weight sliders, the full ranking — and the editor stays yours.

If you set no `editor_password`, the editor is open to everyone. Fine locally,
not for the link you send.

## When something goes wrong

**"GitHub rejected the token"** — the token lacks Contents write, points at the
wrong repo, or has expired. Regenerate and update the secret.

**"Someone else changed the file"** — the file moved on since your session loaded,
usually because you edited from another tab. Reload and redo the edit.

**Commit succeeds but the app looks unchanged** — Streamlit takes a minute or two
to redeploy. Your session already shows the new data, so there's nothing to fix.
