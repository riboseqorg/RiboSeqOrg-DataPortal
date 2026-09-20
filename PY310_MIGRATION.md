# RDP production: sync-prod + Python 3.10 migration

Status as of 2026-09-19. **Nothing has been switched over yet.** Production (`rdp.ucc.ie`) is still
serving the old Python 3.6 server with the old code, and is up.

Plan: tidy up the `sync-prod` branch (including removing RDG), redeploy it to the 3.10 environment,
test it, then run the switch-over.

---

## 1. Background

### Production layout
- Host: `143.239.109.104`, reached via `ssh -J jack@143.239.109.29 {jack,gwips}@143.239.109.104`
  (key auth works for both `jack` and `gwips`; site files are owned by `gwips`, and `jack` can't write them).
- Code: `/home/DATA/www/RiboSeqOrg-DataPortal` (git checkout on branch `live`).
- Request path: Apache (`/etc/apache2/sites-available/rdp-ssl.conf`) → Anubis on `[::1]:8102`
  (`/etc/anubis/rdp.env`, `TARGET=http://localhost:26665`) → `mod_wsgi-express` on `localhost:26665`.
- The `mod_wsgi-express` server is run by the systemd unit `rdp.service` (unit file isn't readable
  without sudo). It currently uses the Python 3.6 venv `riboseq_venv` with server root
  `riboseq_venv/bin/rdpctl`.
- Data files are served from `/home/DATA/RiboSeqOrg-DataPortal-Files/RiboSeqOrg` (`/static2`).

### What was found on production
- `live` had ~60 unpushed commits, but only two held real changes: "updated views" (the CSV export
  returns all samples when no filter is given) and "updated settings for sec" (secure cookies, plus
  the real `SECRET_KEY` hard-coded).
- 11 files had uncommitted edits: the RDG viewer rewrite, Trips-Viz bigWig links, About page entries,
  a Google Analytics tag in `base.html`, `DEBUG = False`, and server-only venv activation in `wsgi.py`.
- Untracked files: the `riboseqorg/RDG/` package, `single_transcript_routes.py`, plus test data
  (`AUG.csv`, `NRAS.csv`, `NARS.json`) and leftovers (`views.py.anmol`, `collapsed_files_11_10_24.txt`,
  `scripts/File_Counting.ipynb`).
- `db.sqlite3` on production is byte-identical to the local copy (14,004 samples, 931 studies).
- Disk: `riboseqorg/debug.log` is 75 GB (not written since Oct 2024) and
  `riboseq_venv/bin/rdpctl/error_log` is 56 GB and still growing.

### Local copies
`~/rdp-prod-snapshot-2026-09-19/`: `live.bundle`, `working_tree.patch`, `files/` (untracked files +
DB), `trips.sqlite` (tripsviz3.6), `gwips_trackDb.tgz`.

---

## 2. What has been done

| Where | What |
|---|---|
| GitHub | Branch `sync-prod` @ `a56eed54`: production's changes on top of `main`. `SECRET_KEY`/`DEBUG` now read from `DJANGO_SECRET_KEY`/`DJANGO_DEBUG` (DEBUG defaults to False). The real key is not in git. |
| Prod | Backup in `/home/DATA/www/rdp-backup-2026-09-19/`: `code.tgz` (no venv or logs), `db.sqlite3`, `working_tree.patch`, `live.bundle`, `py310-freeze.txt`, `pip310.log`. |
| Prod | `/home/DATA/www/rdp-secrets.env` (mode 600, gwips): exports `DJANGO_SECRET_KEY` and `DJANGO_DEBUG=False`. |
| Prod | New env `RiboSeqOrg-DataPortal/riboseq_py310` (conda, Python 3.10.21, Django 3.2.25, mod_wsgi 5.0.2). |
| Prod | New server config `riboseq_py310/rdpctl` (port 26665, 4 processes, gwips, `/static` + `/static2` aliases, secrets via `--envvars-script`, logs rotated at 50 MB). Generated but **not started**. |
| Prod | Test copy `/home/DATA/www/rdp-py310-test` (a56eed54 + DB) with test server config on port 26670 (stopped). |
| Prod | `/home/DATA/www/rdp-cutover/cutover.sh` and `rollback.sh` (not run). |
| Local | `requirements.txt` rewritten with the pinned 3.10 dependencies (uncommitted). |

**Test results for the 3.10 test server** (a56eed54): responses were byte-identical to the live site on
`/`, `/about`, `/samples`, `/studies`, `/RDG/`, `/Sample/…`, `/references/`, `/api/samples/` and the
full CSV export. RDG sequence/manual modes work; gene mode fails **on both 3.6 and 3.10** (it asks
Ensembl for `type=cdna` using a gene ID). That failure goes away once RDG is removed.

---

## 3. To do on `sync-prod` before switching over

### 3a. Remove RDG — done in the working tree (uncommitted)
- Deleted `riboseqorg/RDG/`, `main/templates/main/rdg.html`, `main/single_transcript_routes.py`.
- `views.py`: removed everything after `references()` (RDG imports, `clean_sequence`,
  `get_mature_transcript`, `rdg_view`, the `pplot` stub).
- `urls.py`: removed the `RDG/` route and the commented-out `pplot` route.
- `requirements.txt`: dropped `matplotlib`, `pyahocorasick`, `sqlitedict`, `rich`, `gget`, `gff2bed`.
- Verified locally: `manage.py check` clean, 37 tests pass, main pages return 200, `/RDG/` returns 404.
- On prod, `cutover.sh` no longer checks `/RDG/`. The `riboseq_py310` env still has the RDG packages
  installed. That's harmless, but they can be removed with `pip uninstall`.
- Pre-removal copies of `views.py`, `urls.py`, `rdg.html` and `requirements.txt` are in
  `~/rdp-prod-snapshot-2026-09-19/rdg-removed-backup/`. Git history has the rest.

### 3b. Other tidy-up worth doing on the same branch
- [x] `/pivot/` raised `NameError` because `PIVOT_EXCLUDE` was undefined. Fixed by defining it above
      `pivot()` with the same columns the old `columns2drop` list excluded.
- [ ] Local `settings.py` edits now raise `ImproperlyConfigured` without `DJANGO_SECRET_KEY` unless
      `DJANGO_DEBUG=True`. That's fine for prod, which sets the key via `rdp-secrets.env`.
- [ ] `mod-wsgi-standalone==5.0.2` is installed on prod but not in `requirements.txt` (it compiles
      Apache, so keep it out of the dev requirements or put it in a separate prod file).
- [ ] `utilities.py`: remove the commented-out `/tmp/anmol.txt` debug lines.
- [ ] `base.html`: decide on the Google Analytics tag (`G-1JDHL4P9Y7`, added on prod) and delete the
      commented-out second GA tag and the commented-out "high demand" notice.
- [ ] `models.py` / `custom_track.txt`: confirm the Trips-Viz A-site bigWig switch (`.forward.bw` /
      `.reverse.bw`) is intended. The files must exist under `/home/DATA/RiboSeqOrg-DataPortal-Files`.
- [ ] `views.py`: `sample_select_form` with `download-metadata` + a `run` filter returned the full CSV
      in local testing. Check which parameter name the page actually sends and that filtered
      downloads work.
- [ ] `settings.py`: `ALLOWED_HOSTS = ['*']` could be narrowed to `rdp.ucc.ie`, `localhost`.
      Note that `CSRF_COOKIE_SECURE`/`SESSION_COOKIE_SECURE` break admin login over plain
      `http://localhost` in local dev.
- [ ] Dockerfile still builds on Ubuntu 20.04 / Python 3.8, so move it to 3.10.
- [ ] Commit the 3.10 `requirements.txt` (after the RDG deps are removed).
- [ ] The local working tree also has unrelated uncommitted edits on `sync-prod` (templates, CSS/JS,
      `tests.py`, `utilities.py`, `views.py`, `settings.py`, and untracked `audit/`, `schema/`,
      `main/management/`, `metadata_cleaning.py`). Decide what belongs on this branch.

### 3c. Retest in the 3.10 environment
Once the branch is pushed:
```bash
# on prod as gwips
cd /home/DATA/www/RiboSeqOrg-DataPortal && git fetch origin sync-prod
T=/home/DATA/www/rdp-py310-test
rm -rf $T/riboseqorg && git archive origin/sync-prod riboseqorg | tar x -C $T   # includes the new db.sqlite3
$T/rdpctl/apachectl start
for u in / /about /samples /studies /Sample/DRR244662/ /Study/PRJDB10544/ /references/ /api/samples/ "/sample_select_form/?download-metadata=1" /vocabularies/; do
  echo "$u live=$(curl -s -o /dev/null -w '%{http_code}/%{size_download}' "http://localhost:26665$u") test=$(curl -s -o /dev/null -w '%{http_code}/%{size_download}' "http://localhost:26670$u")"
done
$T/rdpctl/apachectl stop
```
If any removed packages were uninstalled from `riboseq_py310`, check with
`riboseq_py310/bin/python -c "import django, pandas, Bio"`.
`/RDG/` should now return 404.

---

## 4. Switch-over (needs sudo)

`cutover.sh` fetches `origin/sync-prod` itself, so it picks up whatever is on the branch at the time.
Review it first:
```bash
less /home/DATA/www/rdp-cutover/cutover.sh
sudo bash /home/DATA/www/rdp-cutover/cutover.sh
```
What it does:
1. Saves `systemctl cat rdp.service` to `rdp-cutover/rdp.service.before.txt`.
2. Stops `rdp.service` and checks port 26665 is free.
3. Runs `git checkout -f -B sync-prod origin/sync-prod` in the live directory, as gwips (no commit).
4. Writes the drop-in `/etc/systemd/system/rdp.service.d/py310.conf`, which points
   `ExecStart`/`ExecStop`/`ExecReload`/`PIDFile` at `riboseq_py310/rdpctl`.
5. Runs `daemon-reload`, starts the service and curls 8 pages. The site is down for about 10 seconds.

Rollback (restores the 3.6 unit and the exact pre-cutover code):
```bash
sudo bash /home/DATA/www/rdp-cutover/rollback.sh
```
**Note:** `rollback.sh` restores `RDG/` and `single_transcript_routes.py` from the backup, which is
correct because the old code needs them.

The live directory's `wsgi.py` becomes the plain repo version. The new server doesn't need the old
`activate_this`/`sys.path` lines, because it gets `--python-path` and runs inside the 3.10 env.

---

## 5. After the switch-over
- [ ] Watch `riboseq_py310/rdpctl/error_log` for a day.
- [ ] Merge `sync-prod` → `main` → `live`, then move the prod checkout back to `live`.
- [ ] Free about 130 GB once you're happy the new server works:
      `sudo -u gwips truncate -s 0 riboseqorg/debug.log riboseq_venv/bin/rdpctl/error_log`
- [ ] Populate the Trips/GWIPS/RiboCrypt link tables — see [VIEWER_LINKS_SPEC.md](VIEWER_LINKS_SPEC.md).
- [ ] Later: remove the old `riboseq_venv` (53 GB), the `db.sqlite3*` backups, `settings.py.bak/.bkp`,
      `wsgi.py.bak/.bkp`, `views.py.anmol`, and `/home/DATA/www/rdp-py310-test`. Keep `/home/DATA/www/rdp-backup-2026-09-19` until
      things have settled.
- [ ] Remove my key from `~gwips/.ssh/authorized_keys` if you don't want me to keep that access.
