from fastapi import FastAPI, Request
import json
import os
import requests
from datetime import datetime
import pytz
import logging

# Configuration des logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Créer l'application FastAPI
app = FastAPI()

# Configuration GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # format: "username/repo"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents"

# Configuration des dossiers
BASE_FOLDER = "claap_transcripts"
TRANSCRIPTS_FOLDER = "transcripts"
METADATA_FOLDER = "metadata"

def format_date(date_str):
    """Formate la date pour le nom de fichier."""
    try:
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        paris_tz = pytz.timezone("Europe/Paris")
        date_paris = date.astimezone(paris_tz)
        return date_paris.strftime("%Y-%m-%d_%H-%M-%S")
    except Exception as e:
        logger.error(f"Erreur lors du formatage de la date: {e}")
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def save_to_github(content, path, message):
    """Sauvegarde le contenu sur GitHub."""
    try:
        logger.info(f"Tentative de sauvegarde sur GitHub: {path}")
        logger.info(f"Utilisation du repo: {GITHUB_REPO}")
        
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Encoder le contenu en base64
        import base64
        content_bytes = content.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
        
        url = f"{GITHUB_API_URL}/{path}"
        data = {
            "message": message,
            "content": content_base64,
            "branch": "main"
        }
        
        response = requests.put(url, headers=headers, json=data)
        
        if response.status_code in [201, 200]:
            logger.info(f"Fichier sauvegardé avec succès: {path}")
            return True
        else:
            logger.error(f"Erreur lors de la sauvegarde: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde sur GitHub: {e}")
        return False

@app.get("/")
def read_root():
    return {"status": "ok"}

@app.post("/claap-webhook")
async def claap_webhook(request: Request):
    try:
        payload = await request.json()
        logger.info("Webhook reçu : " + json.dumps(payload, indent=2))

        # Vérifier le type d'événement
        event = payload.get("event", {})
        if event.get("type") != "recording_updated":
            logger.info(f"Event ignoré (type: {event.get('type')})")
            return {"status": "ignored", "message": "Event ignoré (non recording_updated)"}

        # Récupérer les données de l'enregistrement
        recording = event.get("recording", {})
        
        # Vérifier s'il y a des transcriptions
        transcripts = recording.get("transcripts", [])
        if not transcripts:
            logger.info("Pas de transcription disponible")
            return {"status": "ok", "message": "No transcripts available"}

        # Traiter chaque transcription
        for transcript in transcripts:
            if transcript.get("isTranscript") and transcript.get("textUrl"):
                text_url = transcript["textUrl"]
                logger.info(f"Téléchargement de la transcription depuis: {text_url}")
                
                response = requests.get(text_url)
                if response.status_code == 200:
                    # Formater le contenu
                    date_str = recording.get("createdAt", datetime.now().isoformat())
                    formatted_date = format_date(date_str)
                    title = recording.get("title", "Sans titre")
                    
                    # Créer le contenu formaté
                    content = f"[{formatted_date}] {title}\n\n{response.text}"
                    
                    # Créer le nom du fichier
                    filename = f"{formatted_date}_{title.replace(' ', '_')[:50]}.txt"
                    path = f"claap_transcripts/transcripts/{filename}"
                    
                    # Sauvegarder sur GitHub
                    if save_to_github(content, path, f"Add transcript: {title}"):
                        logger.info(f"Transcription sauvegardée: {filename}")
                    else:
                        logger.error(f"Échec de la sauvegarde de la transcription: {filename}")
                else:
                    logger.error(f"Erreur lors du téléchargement de la transcription: {response.status_code}")

        return {"status": "success", "message": "Webhook traité avec succès"}

    except Exception as e:
        logger.error(f"Erreur lors du traitement du webhook : {e}")
        return {"status": "error", "message": str(e)} 