# Docker setup

The Docker stack uses the existing root `.env` file. It does not create,
copy, or commit an environment file.

## Start the stack

Ensure your existing `.env` contains the Django settings required by
`DynamicOCR/settings.py`, including `SECRET_KEY`, `DEBUG`, and email settings.
Then start the services:

```bash
docker compose up --build
```

This starts PostgreSQL, Redis, a one-off migration/static-file job, Gunicorn,
a Celery worker, and Celery beat. The application is available on port 8000.

The repository does not currently commit migrations for its local Django apps,
so the one-off setup service uses `migrate --run-syncdb` to create their tables
on a new database. Before a production release, generate and commit normal
Django migrations, then remove `--run-syncdb` from `docker-compose.yml`.

## Container service addresses

For the bundled PostgreSQL and Redis services, use these values in the
existing `.env` when you explicitly set them:

```text
DATABASE_URL=postgres://dynamicocr:dynamicocr@db:5432/dynamicocr
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

If these variables are absent, Compose supplies the same defaults. Values
already present in `.env` take precedence.

## Common commands

```bash
# Start in the background
docker compose up --build -d

# Follow application logs
docker compose logs -f web worker beat

# Stop the stack while retaining database and media volumes
docker compose down

# Remove the stack and all Docker-managed data volumes
docker compose down -v
```

For an internet-facing deployment, put a TLS-terminating reverse proxy in
front of the `web` service and serve the `static_data` volume from that proxy.
