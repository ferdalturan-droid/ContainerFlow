# ContainerFlow — Daily workflow

All commands are typed in **Terminal** (⌘ Cmd + Space → type `Terminal` → Enter).

---

## 1. Start working
| When | Command |
|---|---|
| First, open Docker Desktop | ⌘ Cmd + Space → `Docker` → Enter (wait until the whale icon top-right stops moving) |
| Go to the project | `cd ~/containerflow/super-admin-sayfasi--main` |
| Start the app on your Mac | `./scripts/local-test.sh` → open http://localhost:8080 |

Login locally: any email from `local-logins.txt` (super admin, customer admins, location admins, employees, drivers).
All test users share one password: `LOCAL_TEST_PASSWORD` in `.env.local`.

---

## 2. While developing / testing
| When | Command |
|---|---|
| After every code change (rebuilds + restarts) | `./scripts/local-test.sh` |
| See which files changed | `git status` |
| See errors from the app (stop with Ctrl + C) | `docker logs -f cf-app` |
| Forgot the local password | `grep LOCAL_TEST_PASSWORD .env.local` |
| See the test logins (who is who) | `cat local-logins.txt` |
| See invitation/reset emails the app made | `./scripts/local-test.sh --mails` |
| Wipe local data and create clean test data (~10 min) | `./scripts/local-test.sh --seed` |
| Wipe local data and create demo data: ILK Logistics (basic) + ILK Logistics Premium, Helsingør Forsyning, ARGO, prices, 6 weeks of tours for the reports. Every created user: password `123456` (~10 min) | `./scripts/local-test.sh --demo` |
| Page looks blank/old in the browser | ⌘ Cmd + Shift + R (hard refresh) |
| Price engine unit tests (fast, no server) | `docker exec cf-app sh -c "cd backend && python -m pytest -q tests/test_pricing_engine.py"` |
| End-to-end flows: B2B order, goods, pricing, stops, finish (~1 min, cleans up after itself) | `docker exec -e PW="$(grep '^LOCAL_TEST_PASSWORD=' .env.local \| cut -d= -f2-)" cf-app python /app/backend/tests/e2e/run.py` |
| Only some flows | add names after `run.py`, e.g. `run.py b2b pricing` |

The end-to-end tests (`backend/tests/e2e/`) only run against the **local** database (they refuse anything else). Run them before every deploy - especially after changes to tours, the driver app or pricing.

---

## 3. Save a finished change (on your Mac)
| When | Command |
|---|---|
| Change works locally | `git add -A && git commit -m "what I changed"` |
| See your last saved versions | `git log --oneline -5` |

---

## 4. Put it live (Scaleway)
| Step | Command / action |
|---|---|
| 0. See used versions + which number is next | `./scripts/deploy-scaleway.sh` |
| 1. Build + upload with that number | `./scripts/deploy-scaleway.sh v4` |
| 2. Switch the live site to it | console.scaleway.com → Serverless → Containers → containerflow → image tag → `v4` → Deploy |
| 3. Check | open https://containerflow.dk |
| Something broke after deploy | In the Scaleway console set the tag back to the previous version → Deploy |
| Same demo data on containerflow.dk (DELETES all data there; JSON backup in `~/containerflow-backups`; asks for MONGO_URL + super admin login; a few minutes) | `./scripts/seed-production.sh` (after deploying the latest version) |

---

## 4b. Push-notifikationer til chauffører (én gang)
Chauffører får besked på telefonen (ny tur, haster, ændring, aflysning, besked). Det kræver et VAPID-nøglepar på serveren:
1. Lav nøglerne: `docker run --rm containerflow:test python /app/scripts/gen-vapid.py`. Scriptet ligger i image, når det er bygget fra `main`. Eller kør `python3 scripts/gen-vapid.py`.
2. Læg de to linjer ind som secrets i Scaleway (Container › Environment): `VAPID_PUBLIC_KEY` og `VAPID_PRIVATE_KEY`.
3. Deploy. Skift ikke nøglerne senere uden grund, for så skal alle chauffører slå notifikationer til igen.
Lokalt ligger nøglerne allerede i `.env.local`.

## 5. Back up to GitHub
| When | Command |
|---|---|
| After saving/deploying | `git push && git push --tags` |
| Check if GitHub matches your Mac | `git fetch && git status -sb` ("ahead" = push needed) |

---

## 6. Stop for the day
| When | Command |
|---|---|
| Turn off the local app (data is kept) | `./scripts/local-test.sh --stop` |

---

### Order of a normal change
`local-test.sh` → test in browser → `git commit` → `deploy-scaleway.sh vN` → Scaleway console → `git push`
