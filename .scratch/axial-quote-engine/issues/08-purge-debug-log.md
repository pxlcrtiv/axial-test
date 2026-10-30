# 8: Purge firebase-debug.log from the repo

**What to build:** No log files live in the repo: `firebase-debug.log` (tool debug output containing a personal email) is untracked and gitignored, so `git ls-files` is clean of logs and the "no logs in commits" rule holds going forward.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] `git rm --cached firebase-debug.log` + `.gitignore` covers `*.log`
- [ ] `git ls-files | grep -i log` returns nothing on the branch
- [ ] History rewrite (force-push to strip it from past commits) handled per user's explicit decision — recorded here when made; if declined, this ticket covers untrack-only and the README AI-usage paragraph notes the old commits carry it
