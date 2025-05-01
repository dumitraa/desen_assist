══════════════════════════════════════════════════════════════════
DIGITIZER PLATFORM  •  QUICK COMMAND CHEATSHEET
══════════════════════════════════════════════════════════════════
FILES & FOLDERS
--------------- 
qgis_plugin/                 ← live in every workstation
    config.ini               ← url, layers, local rules
    user_utils.py            ← get_current_user()
    event_tracker.py         ← hooks + send_event()
backend/
    main.py                  ← FastAPI entry-point
    models.py                ← SQLModel (EditEvent)
    database.py              ← create_engine()
    requirements.txt         ← fastapi uvicorn sqlmodel
    events.db                ← SQLite file (dev only)
migrations/                  ← created by “alembic init”
    env.py                   ← points to SQLModel.metadata
    versions/                ← auto-generated *.py revisions
alembic.ini                  ← sqlalchemy.url, script_location

══════════════════════════════════════════════════════════════════
LOCAL DEV  (demo on laptop)
---------------
# activate venv & run API
cd backend
python -m venv venv
venv\Scripts\activate         # Linux: source venv/bin/activate
pip install -r requirements.txt

# launch FastAPI
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# see interactive docs
http://localhost:8000/docs
# open dashboard (served by VS-Code Live-Server etc.)
http://127.0.0.1:3000/dashboard/index.html
# config.ini inside plugin
[backend]
url = http://localhost:8000
timeout = 1

══════════════════════════════════════════════════════════════════
ALEMBIC  (schema migrations)
---------------
# one-time init (already done)
alembic init migrations

# point Alembic to DB  (alembic.ini)
sqlalchemy.url = sqlite:///backend/events.db
# when you change models.py -> new column
alembic revision --autogenerate -m "add user column"
alembic upgrade head

## If revision deleted / DB pointer orphaned
alembic stamp base            # mark current DB as "baseline"

## Quick reset during dev
Ctrl-C     ← stop uvicorn (releases file lock)
del backend\events.db
rm  migrations\versions\*     # fresh history
alembic revision --autogenerate -m "baseline"
alembic upgrade head

══════════════════════════════════════════════════════════════════
PRODUCTION VM  (Ubuntu example)
---------------
# create server
apt update && apt upgrade -y
apt install -y postgresql postgresql-15-postgis-3 python3-venv git caddy

# Postgres bootstrap
sudo -u postgres createuser digitizer_api -P
sudo -u postgres createdb digitizer_db -O digitizer_api
psql -d digitizer_db -c "CREATE EXTENSION postgis;"

# app checkout
mkdir -p /srv/digitizer && cd /srv/digitizer
git clone <repo> .
python3 -m venv venv && . venv/bin/activate
pip install -r backend/requirements.txt gunicorn alembic

# change database.py + alembic.ini
engine = create_engine("postgresql+psycopg2://digitizer_api:***@localhost/digitizer_db")
sqlalchemy.url = postgresql+psycopg2://digitizer_api:***@localhost/digitizer_db

# migrate & start
alembic upgrade head
gunicorn backend.main:app \
        --workers 2 --worker-class uvicorn.workers.UvicornWorker \
        --bind 127.0.0.1:9000 &

# Caddy reverse-proxy  (Caddyfile)
/etc/caddy/Caddyfile
digitizer.mycompany.com {
    reverse_proxy 127.0.0.1:9000
    encode gzip
}

systemctl restart caddy

# systemd service  (optional)
/etc/systemd/system/digitizer.service
[Service]
ExecStart=/srv/digitizer/venv/bin/gunicorn backend.main:app \
          --workers 2 --worker-class uvicorn.workers.UvicornWorker \
          --bind 127.0.0.1:9000
Restart=always
# enable on boot
systemctl daemon-reload
systemctl enable --now digitizer

══════════════════════════════════════════════════════════════════
DAILY OPS
---------------
# pull new code + migrate + restart
ssh ubuntu@server "
  cd /srv/digitizer &&
  git pull &&
  source venv/bin/activate &&
  alembic upgrade head &&
  sudo systemctl restart digitizer
"

# check logs
journalctl -u digitizer -f

# backup Postgres (cron)
pg_dump -Fc digitizer_db > /backups/$(date +%F).dump

══════════════════════════════════════════════════════════════════
DASHBOARD JS SNIPPET  (add user column)
---------------
tbl.innerHTML =
  `<tr>
     <th>time</th><th>user</th><th>layer</th><th>fid</th>
     <th>field</th><th>value</th>
   </tr>` +
  rows.map(e => `
    <tr>
      <td>${e.time}</td><td>${e.user ?? ''}</td><td>${e.layer}</td><td>${e.fid}</td>
      <td>${e.field ?? ''}</td><td>${e.value ?? ''}</td>
    </tr>`
  ).join('');

══════════════════════════════════════════════════════════════════
