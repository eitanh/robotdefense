# Deployment Guide — robotdefense on k3s

Target server: `root@skynet1` (single-node k3s cluster)

## Prerequisites

- k3s installed and running
- Docker installed (for building images)
- `claude` CLI installed on the host and authenticated (`claude --version`)
- `cert-manager` + Traefik installed in the cluster (handles TLS + ingress)

---

## First-time setup

### 1. Create the namespace

```bash
kubectl create namespace robotdefense
```

### 2. Set your real Anthropic API key

Edit `deploy.yaml` and replace `REPLACE_ME`:

```yaml
stringData:
  ANTHROPIC_API_KEY: "sk-ant-..."
```

Or patch it after applying:

```bash
kubectl create secret generic robotdefense-secrets \
  --from-literal=ANTHROPIC_API_KEY="sk-ant-..." \
  --from-literal=POSTGRES_PASSWORD="rd_pass_2026" \
  --from-literal=DATABASE_URL="postgresql://rduser:rd_pass_2026@postgres.robotdefense.svc.cluster.local:5432/robotdefense" \
  -n robotdefense
```

### 3. Build Docker images

Images use `imagePullPolicy: Never` — they must be built locally and imported into k3s containerd.

```bash
# on the server
cd /opt/robotdefense

docker build -t robot-news-crawler:latest ./crawler
docker build -t robotdefense-web:latest ./web

docker save robot-news-crawler:latest | k3s ctr images import -
docker save robotdefense-web:latest   | k3s ctr images import -
```

### 4. Apply the manifest

```bash
kubectl apply -f /opt/robotdefense/k8s/deploy.yaml
```

---

## Redeployment (after code changes)

Sync updated files from your machine, rebuild only what changed, reimport, and reapply.

```bash
# from local machine
rsync -av ./crawler/ root@skynet1:/opt/robotdefense/crawler/
rsync -av ./k8s/     root@skynet1:/opt/robotdefense/k8s/

# on the server — rebuild crawler image
ssh root@skynet1 "
  cd /opt/robotdefense/crawler && \
  docker build -t robot-news-crawler:latest . && \
  docker save robot-news-crawler:latest | k3s ctr images import - && \
  kubectl apply -f /opt/robotdefense/k8s/deploy.yaml
"
```

To force the CronJob to run immediately (for testing):

```bash
kubectl create job --from=cronjob/robot-news-crawler test-run -n robotdefense
kubectl logs -f job/test-run -n robotdefense
```

---

## Verify the deployment

```bash
# all resources
kubectl get all -n robotdefense

# crawler logs (last completed job)
kubectl logs -n robotdefense \
  $(kubectl get pods -n robotdefense -l job-name --sort-by=.metadata.creationTimestamp \
    -o jsonpath='{.items[-1].metadata.name}')

# web logs
kubectl logs -n robotdefense deployment/robotdefense-web

# check articles in DB
kubectl exec -n robotdefense deployment/postgres -- \
  psql -U rduser -d robotdefense -c "SELECT count(*), max(created_at) FROM articles;"
```

---

## Architecture on the server

```
Internet → Traefik (Ingress) → robotdefense-web:8000 → PostgreSQL:5432
                                                  ↑
                              CronJob (*/30 * * * *) — robot-news-crawler
```

| Resource | Details |
|----------|---------|
| Namespace | `robotdefense` |
| Web app | `deployment/robotdefense-web`, port 8000, ClusterIP |
| Database | `deployment/postgres` (PostgreSQL 15), port 5432, **emptyDir** (ephemeral) |
| Crawler | `cronjob/robot-news-crawler`, schedule `*/30 * * * *` |
| Ingress | `robotdefense.io` via Traefik, TLS via cert-manager (Let's Encrypt) |

> **Warning:** Postgres uses `emptyDir` — data is lost if the pod is rescheduled. For production, replace with a `PersistentVolumeClaim`.

---

## Secrets reference

| Key | Value |
|-----|-------|
| `ANTHROPIC_API_KEY` | Anthropic API key (set to `REPLACE_ME` in repo — update before deploy) |
| `POSTGRES_PASSWORD` | `rd_pass_2026` |
| `DATABASE_URL` | `postgresql://rduser:rd_pass_2026@postgres.robotdefense.svc.cluster.local:5432/robotdefense` |
