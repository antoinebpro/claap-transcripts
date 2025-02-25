from fastapi import FastAPI, Request
import json
import os
import requests
from datetime import datetime
import pytz
from git import Repo
import base64

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

def push_to_github(file_path, content, commit_message):
    """
    Pousse un fichier vers GitHub via l'API.
    """
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Encoder le contenu en base64
    content_bytes = content.encode('utf-8')
    content_base64 = base64.b64encode(content_bytes).decode('utf-8')
    
    # Préparer les données
    data = {
        "message": commit_message,
        "content": content_base64
    }
    
    # Vérifier si le fichier existe déjà
    response = requests.get(f"{GITHUB_API_URL}/{file_path}", headers=headers)
    if response.status_code == 200:
        # Si le fichier existe, ajouter le sha pour la mise à jour
        data["sha"] = response.json()["sha"]
    
    # Pousser le fichier
    response = requests.put(
        f"{GITHUB_API_URL}/{file_path}",
        headers=headers,
        json=data
    )
    
    return response.status_code in [200, 201]

def format_date(date_str):
    """
    Convertit la date ISO en format lisible et timestamp.
    """
    try:
        date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        paris_tz = pytz.timezone('Europe/Paris')
        date_paris = date.astimezone(paris_tz)
        formatted_date = date_paris.strftime('%Y-%m-%d_%H-%M-%S')
        return formatted_date, date_paris
    except Exception as e:
        print(f"Erreur lors du formatage de la date : {e}")
        return None, None

def save_transcript(call_data, transcript_text):
    """
    Sauvegarde le transcript et ses métadonnées sur GitHub.
    """
    try:
        call_id = call_data["id"]
        created_at = call_data.get("createdAt")
        formatted_date, _ = format_date(created_at) if created_at else (None, None)
        
        if not formatted_date:
            formatted_date = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        
        # Préparer les métadonnées
        metadata = {
            "call_id": call_id,
            "title": call_data.get("title", "Sans titre"),
            "created_at": created_at,
            "formatted_date": formatted_date,
            "labels": call_data.get("labels", []),
            "coach": call_data.get("owner", {}).get("name", "Coach inconnu"),
            "duration": call_data.get("duration", 0),
            "participants": [p.get("name", "Anonyme") for p in call_data.get("participants", [])]
        }
        
        # Préparer les noms de fichiers
        base_filename = f"{formatted_date}_{call_id}"
        transcript_path = f"{BASE_FOLDER}/{TRANSCRIPTS_FOLDER}/{base_filename}.txt"
        metadata_path = f"{BASE_FOLDER}/{METADATA_FOLDER}/{base_filename}.json"
        
        # Préparer le contenu du transcript
        header = f"Titre: {metadata['title']}\n"
        header += f"Date: {formatted_date}\n"
        header += f"Coach: {metadata['coach']}\n"
        header += f"Labels: {', '.join(metadata['labels'])}\n"
        header += f"Participants: {', '.join(metadata['participants'])}\n"
        header += "-" * 80 + "\n\n"
        transcript_content = header + transcript_text
        
        # Pousser le transcript
        if not push_to_github(
            transcript_path,
            transcript_content,
            f"Add transcript for call {call_id}"
        ):
            raise Exception("Erreur lors du push du transcript")
        
        # Pousser les métadonnées
        if not push_to_github(
            metadata_path,
            json.dumps(metadata, ensure_ascii=False, indent=2),
            f"Add metadata for call {call_id}"
        ):
            raise Exception("Erreur lors du push des métadonnées")
        
        print(f"Transcript et métadonnées sauvegardés pour le call {call_id}")
        return True
        
    except Exception as e:
        print(f"Erreur lors de la sauvegarde : {e}")
        return False

@app.post("/claap-webhook")
async def claap_webhook(request: Request):
    try:
        payload = await request.json()
        print("Webhook reçu :", json.dumps(payload, indent=2))

        if payload.get("event") == "call.updated":
            call_data = payload["data"]
            text_url = call_data.get("textUrl")

            if text_url:
                response = requests.get(text_url)
                if response.status_code == 200:
                    transcript_text = response.text
                    if save_transcript(call_data, transcript_text):
                        return {"status": "success", "message": "Transcript traité avec succès"}
                    else:
                        return {"status": "error", "message": "Erreur lors de la sauvegarde du transcript"}
                else:
                    return {"status": "error", "message": f"Erreur lors du téléchargement du transcript ({response.status_code})"}
            else:
                return {"status": "error", "message": "Aucun textUrl trouvé dans l'événement"}
        else:
            return {"status": "ignored", "message": "Event ignoré (non call.updated)"}

    except Exception as e:
        print(f"Erreur lors du traitement du webhook : {e}")
        return {"status": "error", "message": str(e)} 