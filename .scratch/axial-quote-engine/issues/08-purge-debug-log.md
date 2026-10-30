# 8: Purge firebase-debug.log from the repo

**What to build:** No log files live in the repo: `firebase-debug.log` (tool debug output containing a personal email) is untracked and gitignored, so `git ls-files` is clean of logs and the "no logs in commits" rule holds going forward.

**Blocked by:** None (can start immediately).

**Status:** done

- [x] `git rm --cached firebase-debug.log` + `.gitignore` covers `*.log`
- [x] `git ls-files | grep -i '\.log$'` returns nothing on the branch (wording tightened: plain `grep -i log` also matches this ticket's own filename)
- [x] History rewrite handled per user's explicit decision — **decision recorded 2026-10-30: not force-pushed** (destructive op, no explicit confirmation given; PR #5 left history intact). Fallback applied: untrack-only, and README §6 now notes the old commits still carry the file. A later force-push remains one `git filter-repo` + `push --force` away.
