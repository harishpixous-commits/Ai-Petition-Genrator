# Releases and rollback

Written for whoever is on call. It assumes you can reach GitHub and nothing
else.

## The short version

Something has gone wrong in production and you want the previous version
back:

1. GitHub → **Actions** → **Rollback Production** → **Run workflow**
2. Leave `target` as `production-backup`. Add a one-line reason.
3. **Run workflow**, then approve it if the environment asks.

That is the whole procedure. Everything below is why it works and what to do
when the simple case does not apply.

## What holds what

| | Points at | Moved by |
|---|---|---|
| `main` | the newest code | you, by pushing |
| `production-backup` | the version deployed **before** the current one | the deploy workflow, at the *start* of each deployment |
| `prod-YYYY-MM-DD-NN` | one release that was deployed and answered | the deploy workflow, *after* the health gate |

`production-backup` stays one deployment behind on purpose. If it were
updated after a successful deploy it would point at the code that is live,
which is no use at the moment you need a way back.

So while version B is live, `production-backup` is A. When you deploy C, it
becomes B — and A is still reachable by its tag.

```
  deploy B ─┬─ production-backup := A   (before anything is replaced)
            ├─ deploy B
            └─ tag prod-…-01 := B       (only if B answered)

  deploy C ─┬─ production-backup := B
            ├─ deploy C
            └─ tag prod-…-02 := C

  A is gone from the branch, still at its tag.
```

## There are two rollbacks, and they are for different things

**The automatic one** lives in the deploy workflow. When a fresh deployment
cannot answer `GET /` on the host, the same SSH session puts the previous
image tag back before it reports failure. It is over in under a minute and
needs nobody. It only handles the case the machine can see: the new version
did not come up.

**The manual one** is this workflow. It is for the case the machine cannot
see — the deployment came up, answered every check, and is wrong. Somebody
has to decide that, so somebody has to start it.

## Rolling back

### The usual case

Run **Rollback Production** with `target` = `production-backup`.

The run does the work in two jobs. The first resolves the target and writes
the commit, its message and its date into the run summary. It takes no
credentials and changes nothing. Its only job is to make the approval prompt
on the second one something you can actually judge — "approve a rollback" is
not a decision; "approve going back to 4369524, *Read a phone number said
the way people say it*, 23 Sept" is.

The second job pulls that commit's image, backs up the database, swaps the
container and checks two things:

- `GET /` — the page a citizen loads. Fast, no network calls.
- `GET /api/health` — every configured provider plus the PDF engine. Slow,
  which is why the deploy workflow does not gate on it, but on a rollback it
  is worth the wait: it says the services the restored version needs are
  reachable, not only that the process started.

Both must answer or the run fails.

### Going further back

Put a tag in `target` instead:

```
prod-2026-09-21-02
```

The resolve job accepts a branch name, a tag or a raw commit SHA. If it
cannot find what you typed it stops there and prints the fifteen most recent
release tags, before anyone is asked to approve anything.

### When the image is gone

The host keeps a limited number of images — `latest`, the current tag, the
previous tag and three more — and the rollback pulls from the registry when
the host does not have one. If the registry has dropped it too, the run
stops and says so. Pick a more recent tag; do not try to rebuild the old
commit and call it the same thing, because it will not be.

## What a rollback does not do

It does not touch `main`. No reset, no force-push, no revert commit written
on your behalf. After a rollback, `main` is **ahead of production** — and
that is the correct, visible state. The host serves the older commit until
somebody fixes the newer one and deploys forward.

If the bad change should come out of the branch as well, do that as its own
piece of work:

```bash
git revert <bad commit>          # a new commit that undoes it
git push origin main             # deploys forward, normally
```

`git reset --hard` and `git push --force main` would make the history stop
matching what happened. The record is worth more than a tidy line.

## Settings that are not in this repository

Two things live in GitHub's settings and cannot be committed. Both are
optional; the workflows are correct without them.

**A reviewer on the `production` environment.** Settings → Environments →
`production` → Required reviewers. Without one, a rollback starts as soon as
it is triggered. With one, it waits — and by then the summary already says
what is being approved. The deploy workflow uses the same environment and
gets the same pause.

**Branch protection.** Settings → Branches:

- `main` — block force pushes. The workflows never push to `main`, so
  nothing here can be inconvenienced by it.
- `production-backup` — restrict who can push. The deploy workflow moves it
  with a force push, which is correct for a pointer that goes backwards as
  well as forwards; it is not a branch to develop on. If you protect it,
  allow GitHub Actions.

## Checking without deploying

```bash
git fetch --tags
git log --oneline -1 production-backup      # what a rollback would restore
git tag -l 'prod-*' | tail -5               # recent releases
git show prod-2026-09-23-01                 # who deployed it, when, and why
```

On the host, the file `.env` in the application directory carries
`IMAGE_TAG=<commit sha>` — that is the exact commit currently serving.
