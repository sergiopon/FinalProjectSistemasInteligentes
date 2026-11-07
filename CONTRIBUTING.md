# Working together

Four people work in this repository at the same time. These rules keep one person's work from breaking another's.
Read them once before you start your first spec.

## The rules that matter most

1. **Only Sergio pushes to `main`.** Everyone else works in their own branch and reaches `main` through a pull request that Sergio
   reviews and merges.
2. **One spec, one branch, one owner.** The owner of a spec is in the Progress table of `README.md`.
3. **Touch only the files your spec lists** under "Files to create/modify". If you need a change in a file that
   belongs to another spec, stop and ask its owner. Do not edit it yourself.
4. **Never rewrite shared history.** No `git push --force`, no `--force-with-lease`, no `git reset --hard` on a
   branch someone else has pulled, no `git rebase` of a pushed branch, no deleting other people's branches.
5. **Never skip checks.** No `--no-verify`, no `# noqa`, no `# type: ignore`, no lowered thresholds in
   `pyproject.toml`.
6. **Do not edit these files without Sergio's approval:** `ARCHITECTURE.md`, `security-rules.md`, `CONTEXT.md`,
   `DESIGN.md`, `docs/contracts.md`, `docs/adr/`, `pyproject.toml`, `requirements*.txt`, `config/app.json` and
   everything in `.github/`. They are the source of truth for every spec.

## Before you start a spec

1. `git checkout main && git pull`.
2. Open `specs/README.md`. Your spec must be `Ready`. A spec in `To draft` is not reviewed yet: do not implement it.
   Ask Sergio to review it first.
3. Read the "Depends on" column. Every dependency must be `Implemented` and merged into `main`. If one is not, wait.
   The team diagram linked in `README.md` shows who waits on whom.
4. Read your spec from top to bottom, then the files it cites under "Governing files".

## Doing the work

1. Create the branch from an up-to-date `main`: `git checkout -b feature/NNN-slug`, where `NNN-slug` is the spec file
   name without `.md`. Example: `feature/007-ml-data-cleaning`.
2. Implement exactly what the spec says. A spec is a contract, not a suggestion: do not add features, rename things,
   or change a signature on your own.
3. Write the tests first, see them fail, then write the code. The spec's "Acceptance tests" are the minimum.
4. If the spec is ambiguous, wrong or impossible, stop and message Sergio. Do not guess. If the spec must change,
   the fix goes in its own commit and adds a row to the Corrections table in `specs/README.md`
   (`Date | Spec | Change | Reason`).
5. Commit in small steps with English messages in the imperative: `feat: add comment cleaner`,
   `test: cover empty input`, `docs: fix typo in spec 012`.
6. Keep out of git: `data/`, `reports/`, `models/v*/bundle.joblib`, `.venv/`, `.env`, caches and any secret
   (SEC-10). `git status` must show nothing like these before you commit.

## Checking your work

Run the Gate from the repository root:

```bash
bash scripts/gate.sh
```

It must end with the line `GATE OK`. Until spec 001 is merged the script does not exist; run the commands of the
"Commands" table in `CONTEXT.md` one by one (formatter, linter, type checker, tests, security grep).

Then run the "Definition of Done" checklist at the end of your spec. Every box must be true.

## Delivering

1. Bring your branch up to date: `git fetch && git merge origin/main`. Fix conflicts in your own files only. If a
   conflict is in someone else's file, ask them.
2. Run the Gate again.
3. `git push origin feature/NNN-slug`, then open a pull request into `main`. Fill in the checklist of the template.
4. Sergio reviews. Fix what he asks with new commits on the same branch.
5. After the merge, Sergio (or you, if he asks) marks the spec `Implemented` in `specs/README.md`, runs
   `bash scripts/update_progress.sh` and commits both files, so the README progress table stays correct.

## Who owns which files

| Person | Areas |
|---|---|
| Sergio Ponce | `pyproject.toml`, `requirements*.txt`, `config/`, `scripts/`, `api/domain/`, `api/ports/`, `tests/architecture/`, `tests/unit/domain/`, `tests/unit/ports/`, `README.md`, benchmark |
| Andres Acosta | `ml/` data cleaning, split, representations, model selection, conformal, gold set and gold evaluation, with their tests |
| Jose David Ruano | `ml/` aspects, artifact registry and train CLI; `api/adapters/` settings, logging, model store, sklearn models and text, with their tests |
| Felipe Moncada | `api/adapters/` monitoring, HTTP and CSV; `api/application/`, `api/main.py`, `web/`, Docker files, with their tests |

The exact file list of each spec is in its "Files to create/modify" section; that list wins over this table.

## When something goes wrong

- You committed to the wrong branch: do not force anything. Tell Sergio and describe what happened.
- You pushed something that should not be public (a key, personal data): tell Sergio right away, before anything
  else. Removing it from the history is a decision for him.
- The Gate fails on code you did not write: do not touch it. Report the failing command and its last output line to
  the owner of that file.
