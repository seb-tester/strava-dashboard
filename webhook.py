from fastapi import FastAPI, Request, Query
import subprocess
import asyncio
import hmac
import hashlib
from notifier import notify

app = FastAPI()

VERIFY_TOKEN   = "strava_webhook_token"
GITHUB_SECRET  = "strava_deploy_secret"

def verify_github_signature(payload: bytes, signature: str) -> bool:
    expected = "sha256=" + hmac.new(
        GITHUB_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return {"hub.challenge": hub_challenge}
    return {"error": "invalid token"}

@app.post("/webhook")
async def receive_webhook(request: Request):
    data = await request.json()
    print(f"Webhook reçu: {data}")
    object_type = data.get("object_type")
    object_id   = str(data.get("object_id", ""))
    aspect_type = data.get("aspect_type")
    if object_type == "activity" and aspect_type == "create" and object_id:
        async def delayed_sync():
            await asyncio.sleep(10)
            subprocess.Popen([
                "/home/pi/strava/venv/bin/python3",
                "/home/pi/strava/strava_sync.py",
                "--activity-id", object_id
            ])
        asyncio.create_task(delayed_sync())
    elif object_type == "activity" and aspect_type == "delete" and object_id:
        async def delayed_delete():
            await asyncio.sleep(5)
            subprocess.Popen([
                "/home/pi/strava/venv/bin/python3",
                "/home/pi/strava/strava_sync.py",
                "--delete-activity-id", object_id
            ])
        asyncio.create_task(delayed_delete())
    return {"status": "ok"}

@app.post("/deploy")
async def deploy(request: Request):
    body = await request.body()
    sig  = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(body, sig):
        return {"error": "signature invalide"}
    async def do_deploy():
        subprocess.run(["git", "-C", "/home/pi/strava", "pull", "origin", "main"])
        subprocess.run(["/home/pi/strava/venv/bin/python3", "/home/pi/strava/strava_dashboard.py"])
        notify("🚀 Déploiement strava-dashboard", "git pull + redémarrage en cours…", tags=["rocket"])
        subprocess.run(["sudo", "systemctl", "restart", "strava-webhook"])
    asyncio.create_task(do_deploy())
    print("🚀 Déploiement déclenché par GitHub")
    return {"status": "déploiement en cours"}

@app.get("/")
async def dashboard():
    try:
        with open("/home/pi/strava/strava_output/dashboard.html", "r") as f:
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=f.read())
    except:
        return {"status": "Strava Pi en ligne"}
