# Server Cheatsheet
---

## Workflow

```text
LOCAL ── git push ──► GIT REMOTE ◄── git pull ── VPS
                                      │
                                      ▼
                                   restart
                                      │
                                      ▼
                                   LIVE APP
```

## tmux for process supervision

### (re)attach to the session

```bash
tmux attach -t app        
```

If the session doesn’t exist yet:

```bash
tmux new -s app
```

### Stop the running server

**Ctrl +C**

### start (or restart) the server

```bash
cd ~/desen_assist
source venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### detach and keep it running

Press **Ctrl +b** (release) then **d**.  
You’ll see `[detached]` – that means the session is staying alive.

---

## Troubleshooting quickies

- **Port already in use**  
  `lsof -i :8000`

- **Virtualenv missing deps**  
  `pip install -r requirements.txt` inside the venv

- **Cannot attach**  
  Session crashed – recreate with `tmux new -s app`
