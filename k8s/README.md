# Kubernetes (Optional)

This repository’s **primary** and **required** local development workflow is **Docker Compose** (see the main `README.md`).

The manifests in `/k8s` are provided **only** to demonstrate how the **same Docker image** and **same environment variables** used by Docker Compose could be deployed to a Kubernetes cluster.

- Kubernetes is **not required** to run or evaluate this project.
- No application code changes are needed for Kubernetes.
- Docker Compose remains fully functional and the default.

## What’s included

- `deployment.yaml`: Deploys the FastAPI container (port `8000`) and loads env via `envFrom`.
- `service.yaml`: A `ClusterIP` service exposing the API internally on port `8000`.
- `configmap.yaml`: Non-secret env vars (mirrors `.env.example` variable names where applicable).
- `secret.example.yaml`: **Example only** — shows required secret keys; do not commit real secrets.

## How this relates to Docker Compose

Docker Compose (`docker-compose.yml`) does:

- Build the image from the existing `Dockerfile`
- Run the API on port `8000`
- Load environment variables from `.env`

Kubernetes mirrors that by:

- Using the **same container image** (built from the same `Dockerfile`)
- Exposing port `8000` from the container
- Loading the same env var names via:
  - `ConfigMap` (non-secret values)
  - `Secret` (secret values)

## Deploying (conceptual)

These manifests assume you have:

- Access to **any** Kubernetes cluster and `kubectl`
- A Postgres instance reachable from the cluster (managed DB, separate Helm chart, separate manifests, etc.)

### 1) Build and publish the same Docker image

In Compose, the `api` service uses `build: .`. In Kubernetes you must reference an image by name.

Build and tag:

```bash
docker build -t ascertain-task:latest .
```

Then either:

- Push it to a registry your cluster can pull from (recommended), and update `k8s/deployment.yaml` `spec.template.spec.containers[0].image`
- Or (cluster-dependent) load the image into your cluster runtime

> This repo intentionally does **not** require Minikube/Kind/any specific cluster to run locally.

### 2) Create the Secret (do not commit real secrets)

An example Secret is provided:

```bash
cp k8s/secret.example.yaml k8s/secret.yaml
```

Edit `k8s/secret.yaml` and set:

- `DATABASE_URL` (pointing to your Postgres host/service)
- `OPENAI_API_KEY` (if using OpenAI-backed summary generation)

**Important safety note:** avoid running `kubectl get secret ... -o yaml` / `-o json` in shared logs.
It will print base64-encoded values and may also include annotations that contain the last-applied configuration.

Alternatively, create it imperatively (recommended for demos so you don’t store plaintext secret values
in a “last-applied” annotation):

```bash
kubectl delete secret ascertain-secrets --ignore-not-found
kubectl create secret generic ascertain-secrets \
  --from-literal=DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@HOST:5432/ascertain' \
  --from-literal=OPENAI_API_KEY='...'
```

### 3) Apply the manifests

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

### 4) Access the API (example)

Port-forward the service:

```bash
kubectl port-forward svc/ascertain-api 8000:8000
```

Then:

```bash
curl -s localhost:8000/health
```

## Local demo (Kind) — optional smoke test

If you already use [Kind](https://kind.sigs.k8s.io/) locally, the commands below provide a quick end-to-end smoke test
against the Kubernetes manifests in this repo. This is **optional** and does not replace Docker Compose.

### 1) Create/use a Kind cluster

```bash
kind create cluster --name kind
kubectl config use-context kind-kind
kubectl get nodes
```

### 2) Build the image and load it into Kind

`k8s/deployment.yaml` uses `image: ascertain-task:latest`, so build and load that tag:

```bash
docker build -t ascertain-task:latest .
kind load docker-image ascertain-task:latest --name kind
```

### 3) Demo Postgres inside the cluster (so `@db:5432` works like Compose)

Docker Compose provides a `db` hostname automatically. In Kubernetes, you need a Service named `db` (or update
`DATABASE_URL` to point at a real Postgres host).

For a **local demo only**, you can run Postgres in-cluster:

```bash
kubectl apply -f - <<'YAML'
apiVersion: v1
kind: Service
metadata:
  name: db
spec:
  selector:
    app: db
  ports:
    - port: 5432
      targetPort: 5432
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: db
spec:
  replicas: 1
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
    spec:
      containers:
        - name: postgres
          image: postgres:16
          ports:
            - containerPort: 5432
          env:
            - name: POSTGRES_USER
              value: postgres
            - name: POSTGRES_PASSWORD
              value: postgres
            - name: POSTGRES_DB
              value: ascertain
YAML

kubectl rollout status deploy/db
```

### 4) Create the Secret + apply the app manifests

For a local demo, create the Secret imperatively (avoids storing plaintext in a “last-applied” annotation):

```bash
kubectl delete secret ascertain-secrets --ignore-not-found
kubectl create secret generic ascertain-secrets \
  --from-literal=DATABASE_URL='postgresql+asyncpg://postgres:postgres@db:5432/ascertain' \
  --from-literal=OPENAI_API_KEY='dummy-not-used-for-health'
```

Then apply the manifests and wait for readiness:

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

kubectl rollout status deploy/ascertain-api
```

### 5) Port-forward + test endpoints

```bash
kubectl port-forward svc/ascertain-api 8000:8000
```

In another terminal:

```bash
curl -s http://localhost:8000/health

curl -s -X POST http://localhost:8000/patients \
  -H 'Content-Type: application/json' \
  -d '{"name":"K8s Smoke Test Patient","date_of_birth":"1990-01-01"}'

curl -s 'http://localhost:8000/patients?name=k8s&limit=10'
```

### Cleanup (demo-only)

```bash
kubectl delete deploy/ascertain-api svc/ascertain-api cm/ascertain-config secret/ascertain-secrets --ignore-not-found
kubectl delete deploy/db svc/db --ignore-not-found
```

## Volumes & persistence (conceptual mapping)

Docker Compose uses local volumes/bind-mounts for convenience:

- **Postgres data**: `postgres_data` named volume
- **API source code** (dev mode): bind-mount `.:/app` via `docker-compose.override.yml`
- **Patient notes files**: stored under `./data/notes` inside the container filesystem

Kubernetes equivalents in a real deployment:

- **Postgres data**: a `PersistentVolumeClaim` (or, more commonly, a managed Postgres service outside the cluster)
- **API source code**: you typically **do not** bind-mount code; you deploy immutable images
- **Patient notes**:
  - For demo: `k8s/deployment.yaml` uses `emptyDir` mounted at `/app/data/notes` (ephemeral; pod restart wipes it)
  - For production: use a `PersistentVolumeClaim` or store note blobs in object storage (e.g., S3/GCS/Azure Blob) and keep only metadata in Postgres

> This repo intentionally keeps Kubernetes storage **minimal** to avoid requiring a specific local cluster or PV setup.


