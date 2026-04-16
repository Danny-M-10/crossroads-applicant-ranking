# Deploying the applicant ranking app (crossroads server)

This app is built by Docker Compose in **`crossroads-resume-grader`**, using this repository as the image build context.

## Paths (production server)

| Item | Path |
|------|------|
| Git checkout | `~/internal_crossroads_Candidate_Ranking_Application_v3.0.1` |
| Compose project | `~/crossroads-resume-grader` |
| Compose files | `docker-compose.prod.yml` + `docker-compose.yml` |
| Host health URL | `http://127.0.0.1:9011/health` (maps to app port 8000) |
| Public site | Configured in compose (`BASE_URL`); typically behind NPM |

Secrets live in **`~/internal_crossroads_Candidate_Ranking_Application_v3.0.1/.env`** (gitignored). Compose also bind-mounts that file read-only into the container.

## Routine update (after merging to `main`)

From the server as `crossroadsadmin`:

```bash
~/internal_crossroads_Candidate_Ranking_Application_v3.0.1/scripts/deploy-server.sh
```

Or manually:

```bash
cd ~/internal_crossroads_Candidate_Ranking_Application_v3.0.1
git pull --ff-only origin main
cd ~/crossroads-resume-grader
docker compose -f docker-compose.prod.yml -f docker-compose.yml build backend
docker compose -f docker-compose.prod.yml -f docker-compose.yml up -d --no-deps backend
curl -sf http://127.0.0.1:9011/health
```

`--no-deps` avoids restarting the Postgres service or other stacks.

## Git authentication (SSH deploy key)

The server uses HTTPS by default if no deploy key is registered. For a **read-only deploy key**:

1. On the server, the key pair is at `~/.ssh/github_internal_crossroads_deploy` (public key: `.pub`).
2. In GitHub: **Repository → Settings → Deploy keys → Add deploy key** — paste the **public** key, enable **Allow read access** only.
3. In the app checkout:

   ```bash
   cd ~/internal_crossroads_Candidate_Ranking_Application_v3.0.1
   git remote set-url origin git@github.com:Danny-M-10/crossroads-applicant-ranking.git
   git config core.sshCommand "ssh -i $HOME/.ssh/github_internal_crossroads_deploy -o IdentitiesOnly=yes"
   git fetch origin
   ```

If `~/.ssh/config` is not writable (e.g. owned by root), repo-local `core.sshCommand` (step 3) is enough; no global SSH config change is required.

## One-time migration notes

The previous non-git tree was renamed to `~/internal_crossroads_Candidate_Ranking_Application_v3.0.1.pre-git-*`. After verifying production, remove that backup directory. Env and `data/` snapshots were saved under `~/backups/` during migration.
