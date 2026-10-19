# Aster OCI operations

Deployment directory: `/opt/apps/aster`  
Public URL: `https://140.245.234.125/aster/`  
Compose project: `aster`  
Gateway alias: `aster-app:8000`

Run these commands from `/opt/apps/aster`:

```bash
# Status
docker compose -f deploy/compose.production.yml ps -a

# Start existing containers after a routine stop
docker compose -f deploy/compose.production.yml start postgres qdrant app

# Stop Aster only (keeps volumes)
docker compose -f deploy/compose.production.yml stop

# Rebuild and restart the web application after source changes
docker compose -f deploy/compose.production.yml build app
docker compose -f deploy/compose.production.yml up -d --no-deps app

# Follow application logs
docker compose -f deploy/compose.production.yml logs -f --tail=200 app

# Apply schema migrations after an update
docker compose -f deploy/compose.production.yml run --rm migrate

# Publish a fresh immutable knowledge snapshot after corpus changes
docker compose -f deploy/compose.production.yml run --rm knowledge

# Create a retained PostgreSQL backup
./deploy/backup.sh
```

For a fresh installation, start PostgreSQL and Qdrant, run `migrate` and
`knowledge` once, then start `app`. The initialization services use the
`init` profile so a routine `up` cannot accidentally republish the corpus.

The persistent volumes are `aster-postgres-data` and `aster-qdrant-data`.
Neither database service publishes a host port. Only `aster-app` joins the
external `shared-gateway` network.

To restore PostgreSQL, stop the Aster application, create a safety backup,
and restore into a fresh or deliberately emptied `aster` database:

```bash
docker compose -f deploy/compose.production.yml stop app
cat backups/postgres-YYYYMMDDTHHMMSSZ.dump | \
  docker compose -f deploy/compose.production.yml exec -T postgres \
  pg_restore -U aster -d aster --clean --if-exists
docker compose -f deploy/compose.production.yml start app
```

Test restores against a disposable database before using this procedure on
production. Qdrant knowledge can be reconstructed with the `knowledge`
service; snapshot the `aster-qdrant-data` volume separately if faster recovery
is required.

Required secrets live in `deploy/production.env` with mode `600`. Required
runtime values are `DATABASE_URL`, `POSTGRES_PASSWORD`, `JWT_SECRET`,
`CHATGROQ_API_KEY`, and `COHERE_API_KEY`. The file also defines the private
Qdrant URL, trusted public origin, `/aster` cookie path, quotas, and timeouts.
