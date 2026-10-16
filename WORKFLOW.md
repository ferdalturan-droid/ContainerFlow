# ContainerFlow — Daily workflow

All commands are typed in **Terminal** (⌘ Cmd + Space → type `Terminal` → Enter).

---

## 1. Start working
| When | Command |
|---|---|
| First, open Docker Desktop | ⌘ Cmd + Space → `Docker` → Enter (wait until the whale icon top-right stops moving) |
| Go to the project | `cd ~/containerflow/super-admin-sayfasi--main` |
| Start the app on your Mac | `./scripts/local-test.sh` → open http://localhost:8080 |

Login locally: `doganmiketuran@gmail.com` + the local password.

---

## 2. While developing / testing
| When | Command |
|---|---|
| After every code change (rebuilds + restarts) | `./scripts/local-test.sh` |
| See which files changed | `git status` |
| See errors from the app (stop with Ctrl + C) | `docker logs -f cf-app` |
| Forgot the local password | `grep LOCAL_SUPERADMIN_PASSWORD .env.local` |
| Wipe local test data and start fresh | `./scripts/local-test.sh --reset` |
| Page looks blank/old in the browser | ⌘ Cmd + Shift + R (hard refresh) |

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
| 1. Build + upload (use the next number every time) | `./scripts/deploy-scaleway.sh v4` |
| 2. Switch the live site to it | console.scaleway.com → Serverless → Containers → containerflow → image tag → `v4` → Deploy |
| 3. Check | open https://containerflow.dk |
| Which versions were deployed | `git tag -l "deploy-*"` |
| Something broke after deploy | In the Scaleway console set the tag back to the previous version → Deploy |

---

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
