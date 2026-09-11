ALERTE LOGEMENTS CROUS - ILE-DE-FRANCE
========================================

1) Installer les dependances :
   pip install -r requirements.txt

2) (Optionnel) Activer les alertes par email :
   Definir ces variables d'environnement avant de lancer le script
   (par exemple dans un fichier .env, ou directement dans le terminal) :

     CROUS_EMAIL_FROM=ton.adresse@gmail.com
     CROUS_EMAIL_PASSWORD=xxxxxxxxxxxxxxxx   (mot de passe d'application Gmail)
     CROUS_EMAIL_TO=ton.adresse@gmail.com

   Sans ces variables, le script affiche simplement les nouveaux
   logements dans le terminal - ca fonctionne deja tel quel.

3) Lancer une verification :
   python crous_alerte.py

4) Lancer une surveillance en continu (verifie toutes les 15 min) :
   python crous_alerte.py --loop

5) Pour une surveillance 24h/24 sans garder ton PC allume, deux options :
   - Planifier "python crous_alerte.py" (sans --loop) toutes les 15 min
     via le Planificateur de taches (Windows) ou cron (Mac/Linux).
   - Heberger le script sur un service gratuit type GitHub Actions
     (workflow programme), un PC/Raspberry Pi allume en permanence,
     ou un petit serveur.

A savoir :
- Le site du CROUS change periodiquement l'ID de "phase" de recherche
  (SEARCH_TOOL_ID dans le script). Si le script ne trouve plus rien,
  verifie l'ID actuel sur https://trouverunlogement.lescrous.fr/api/fr/tools
- Le fichier logements_connus.json garde en memoire les logements deja
  vus pour ne signaler que les nouveautes. Supprime-le si tu veux
  reinitialiser (tu recevras alors tous les logements actuels comme
  "nouveaux" au prochain lancement).
