#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alerte logements CROUS - Ile-de-France
========================================
Surveille trouverunlogement.lescrous.fr et preveither par email (ou juste
dans le terminal) des qu'un nouveau logement apparait dans la zone visee.

Installation :
    pip install requests beautifulsoup4

Utilisation :
    python crous_alerte.py            # une seule verification
    python crous_alerte.py --loop     # tourne en continu (Ctrl+C pour arreter)

Pour une surveillance permanente sans garder un PC allume, planifie
l'execution via le Planificateur de taches (Windows), cron (Linux/Mac),
ou un workflow GitHub Actions programme (recherche "github actions schedule").
"""

import json
import os
import re
import smtplib
import sys
import time
from dataclasses import dataclass
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Set

import requests
from bs4 import BeautifulSoup

# ============================== CONFIGURATION ==============================

# ID de la "phase" de recherche en cours sur le site. Le site en change
# selon la periode (phase principale, complementaire, etc). Pour connaitre
# l'ID actuel, ouvre : https://trouverunlogement.lescrous.fr/api/fr/tools
# (au 11/09/2026, la phase en cours est l'ID 47 : "Phase complementaire 2026-2027")
SEARCH_TOOL_ID = 47

# Rectangle geographique (bounds) au format "lon_NO_lat_NO_lon_SE_lat_SE".
# Celui-ci couvre l'ensemble de l'Ile-de-France au sens large.
# Tu peux en obtenir un plus precis en faisant une recherche par ville sur
# le site, puis en cliquant sur "Rechercher dans la zone" (carte) : l'URL
# affichee dans le navigateur contient le bon parametre "bounds=...".
BOUNDS = "1.4_49.3_3.6_48.0"

# Filtre optionnel : prix maximum en euros (laisser None pour ignorer)
PRIX_MAX = None  # ex: 500

# Frequence de verification en secondes (utilise seulement avec --loop)
INTERVALLE_SECONDES = 15 * 60  # 15 minutes

# Fichier ou sont memorises les logements deja vus, pour ne signaler
# que les nouveautes d'une execution a l'autre.
FICHIER_ETAT = Path(__file__).parent / "logements_connus.json"

# --- Envoi d'email (optionnel). Laisse ces variables vides pour
#     desactiver l'email : le script affichera juste les resultats
#     dans le terminal. Pour Gmail, EMAIL_MOT_DE_PASSE doit etre un
#     "mot de passe d'application" (pas ton mot de passe normal). ---
EMAIL_EXPEDITEUR = os.environ.get("CROUS_EMAIL_FROM", "")
EMAIL_MOT_DE_PASSE = os.environ.get("CROUS_EMAIL_PASSWORD", "")
EMAIL_DESTINATAIRE = os.environ.get("CROUS_EMAIL_TO", "")
SMTP_SERVEUR = os.environ.get("CROUS_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("CROUS_SMTP_PORT", "587"))

# ==============================================================================

BASE_URL = "https://trouverunlogement.lescrous.fr"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CrousAlerteBot/1.0)"}


@dataclass
class Logement:
    id: str
    nom: str
    adresse: str
    prix: str
    url: str


def recuperer_page(numero_page: int) -> BeautifulSoup:
    url = f"{BASE_URL}/tools/{SEARCH_TOOL_ID}/search"
    params = {"bounds": BOUNDS}
    if numero_page > 1:
        params["page"] = numero_page
    if PRIX_MAX:
        params["price"] = PRIX_MAX
    reponse = requests.get(url, params=params, headers=HEADERS, timeout=20)
    reponse.raise_for_status()
    return BeautifulSoup(reponse.text, "html.parser")


def extraire_logements(soup: BeautifulSoup) -> List[Logement]:
    """Extrait les logements a partir des liens vers les fiches
    ("/tools/<id>/accommodations/<id_logement>"). Cette approche est
    robuste aux changements de mise en page puisqu'elle ne depend que
    de la structure des URLs, pas des classes CSS."""
    logements = []
    vus = set()
    for lien in soup.select(f'a[href*="/tools/{SEARCH_TOOL_ID}/accommodations/"]'):
        href = lien.get("href", "")
        match = re.search(r"/accommodations/(\d+)", href)
        if not match:
            continue
        id_logement = match.group(1)
        if id_logement in vus:
            continue
        vus.add(id_logement)

        nom = lien.get_text(strip=True) or f"Logement {id_logement}"

        # On remonte au conteneur de la carte pour recuperer prix/adresse
        carte = lien.find_parent("li") or lien.find_parent("div") or lien.parent
        texte_carte = carte.get_text(" ", strip=True) if carte else ""

        prix_match = re.search(r"(\d[\d\s]*(?:,\d+)?\s?€)", texte_carte)
        prix = prix_match.group(1) if prix_match else "?"

        adresse_match = re.search(r"\d{5}\s+[A-ZÀ-Ü][\w\s\-']+", texte_carte)
        adresse = adresse_match.group(0).strip() if adresse_match else ""

        url_complete = BASE_URL + href if href.startswith("/") else href

        logements.append(Logement(id=id_logement, nom=nom, adresse=adresse, prix=prix, url=url_complete))
    return logements


def nombre_de_pages(soup: BeautifulSoup) -> int:
    titre = soup.title.string if soup.title else ""
    match = re.search(r"page (\d+) sur (\d+)", titre or "")
    if match:
        return int(match.group(2))
    return 1


def recuperer_tous_les_logements() -> List[Logement]:
    premiere_page = recuperer_page(1)
    total_pages = nombre_de_pages(premiere_page)
    tous = extraire_logements(premiere_page)
    for page in range(2, total_pages + 1):
        time.sleep(1)  # on ne veut pas marteler le serveur du CROUS
        tous.extend(extraire_logements(recuperer_page(page)))
    return tous


def charger_ids_connus() -> Set[str]:
    if FICHIER_ETAT.exists():
        return set(json.loads(FICHIER_ETAT.read_text(encoding="utf-8")))
    return set()


def sauvegarder_ids_connus(ids: Set[str]) -> None:
    FICHIER_ETAT.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def envoyer_email(nouveaux: List[Logement]) -> None:
    if not (EMAIL_EXPEDITEUR and EMAIL_MOT_DE_PASSE and EMAIL_DESTINATAIRE):
        return
    corps = "\n\n".join(f"{l.nom}\n{l.adresse}\n{l.prix}\n{l.url}" for l in nouveaux)
    message = MIMEText(corps, _charset="utf-8")
    message["Subject"] = f"Nouveau(x) logement(s) CROUS : {len(nouveaux)}"
    message["From"] = EMAIL_EXPEDITEUR
    message["To"] = EMAIL_DESTINATAIRE

    with smtplib.SMTP(SMTP_SERVEUR, SMTP_PORT) as serveur:
        serveur.starttls()
        serveur.login(EMAIL_EXPEDITEUR, EMAIL_MOT_DE_PASSE)
        serveur.send_message(message)


def verifier_une_fois() -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Verification en cours...")
    try:
        logements_actuels = recuperer_tous_les_logements()
    except requests.RequestException as erreur:
        print(f"Erreur reseau : {erreur}")
        return

    ids_connus = charger_ids_connus()
    nouveaux = [l for l in logements_actuels if l.id not in ids_connus]

    if nouveaux:
        print(f"{len(nouveaux)} nouveau(x) logement(s) trouve(s) :")
        for logement in nouveaux:
            print(f"  - {logement.nom} ({logement.prix}) - {logement.adresse}\n    {logement.url}")
        envoyer_email(nouveaux)
    else:
        print(f"Rien de nouveau ({len(logements_actuels)} logements au total dans la zone).")

    sauvegarder_ids_connus({l.id for l in logements_actuels} | ids_connus)


def main() -> None:
    if "--loop" in sys.argv:
        print(f"Surveillance en continu, toutes les {INTERVALLE_SECONDES // 60} minutes. Ctrl+C pour arreter.")
        while True:
            verifier_une_fois()
            time.sleep(INTERVALLE_SECONDES)
    else:
        verifier_une_fois()


if __name__ == "__main__":
    main()
