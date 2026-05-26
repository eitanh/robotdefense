# k8s

Single manifest (`deploy.yaml`) that deploys the full stack to a `robotdefense` namespace.

## Resources

| Resource | Kind | Description |
|----------|------|-------------|
| `robotdefense-secrets` | Secret | Postgres password, DATABASE_URL, ANTHROPIC_API_KEY |
| `postgres` | Deployment + Service | PostgreSQL 15, data on `emptyDir` (ephemeral) |
| `robotdefense-web` | Deployment + Service | FastAPI web app on port 8000 |
| `robot-news-crawler` | CronJob | Runs crawler every hour (`0 * * * *`) |
| `robotdefense` | Ingress | Traefik + Let's Encrypt TLS → `robotdefense.io` |

## Deploy

```bash
# Replace the placeholder API key before applying
sed -i '' 's/REPLACE_ME/sk-ant-...' deploy.yaml

kubectl create namespace robotdefense
kubectl apply -f deploy.yaml
```

## Notes

- Postgres uses `emptyDir` — data is lost if the pod restarts. Use a PVC for persistence.
- Images are pulled with `imagePullPolicy: Never` — build them locally before deploying to a local cluster.
- The crawler reads `ANTHROPIC_API_KEY` from the secret but the Claude CLI on bare metal manages its own auth via `~/.claude`.
