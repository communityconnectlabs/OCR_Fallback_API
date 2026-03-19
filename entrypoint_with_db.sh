#!/bin/sh
set -e

PG_VERSION=$(ls /usr/lib/postgresql/)
PG_DATA=/var/lib/postgresql/data
PG_BIN=/usr/lib/postgresql/$PG_VERSION/bin

# Dynamically generate the supervisord.conf
cat > /app/supervisord.conf <<EOF
[supervisord]
nodaemon=true
logfile=/var/log/supervisord.log

[program:postgres]
command=/usr/lib/postgresql/$PG_VERSION/bin/postgres -D /var/lib/postgresql/data
user=postgres
autostart=true
autorestart=true
stdout_logfile=/var/log/postgres.log
stderr_logfile=/var/log/postgres.log

[program:api]
command=uvicorn fallback_project.main_with_db:app --host 0.0.0.0 --port 8080
directory=/app
autostart=true
autorestart=true
stdout_logfile=/var/log/api.log
stderr_logfile=/var/log/api.log
EOF

# Initialize DB cluster if first run
if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    echo "Initializing PostgreSQL cluster..."
    su postgres -c "$PG_BIN/initdb -D $PG_DATA"
    su postgres -c "$PG_BIN/pg_ctl -D $PG_DATA start"
    sleep 3
    su postgres -c "psql -c \"CREATE USER snapuser WITH PASSWORD 'pwforsnap';\""
    su postgres -c "psql -c \"CREATE DATABASE nutrition_and_ingredients_db OWNER snapuser;\""
    su postgres -c "psql -d nutrition_and_ingredients_db -c \"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO snapuser;\""
    su postgres -c "psql -d nutrition_and_ingredients_db -f /app/init.sql"
    su postgres -c "psql -d nutrition_and_ingredients_db -c \"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO snapuser;\""
    su postgres -c "psql -d nutrition_and_ingredients_db -c \"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO snapuser;\""
    su postgres -c "$PG_BIN/pg_ctl -D $PG_DATA stop"
fi

echo "Starting services..."
exec supervisord -c /app/supervisord.conf