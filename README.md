# Lyra Bot — bot de modération Discord

Bot Python en français, avec commandes slash (`/`) et commandes texte (préfixe strict `++`), et stockage SQLite local. Python 3.11 ou supérieur recommandé. `++help` (ou `/help`) liste toutes les commandes.

## Installation

1. Crée une application nommée **Lyra Bot** sur https://discord.com/developers/applications puis ouvre **Bot** pour obtenir son token. Ne partage jamais ce token dans un message ou une capture.
2. Dans **OAuth2 → URL Generator**, sélectionne `bot` et `applications.commands`. Accorde : Voir les salons, Envoyer des messages, Envoyer des messages dans les fils, Intégrer des liens, Voir les anciens messages, Gérer les messages, Expulser des membres, Bannir des membres, Exclure temporairement des membres, ainsi que **Se connecter** et **Parler** (pour la musique). La permission Administrateur n’est pas nécessaire.
3. Ouvre le lien généré pour inviter le bot. Dans les paramètres du serveur, place son rôle au-dessus des membres à modérer. Le rôle du modérateur doit lui aussi être au-dessus de sa cible, sauf pour le propriétaire.
4. Installe Python, puis ouvre un terminal dans le dossier LyraBot décompressé.

Windows :

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe bot.py
```

Linux / macOS :

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Éditer .env avant de lancer le bot
.venv/bin/python bot.py
```

Dans `.env`, remplace la valeur `DISCORD_TOKEN` par ton token. Pour un seul serveur, renseigne aussi `GUILD_ID` : active le mode développeur dans les paramètres Discord, puis clic droit sur le serveur → Copier l’identifiant. Cela permet de synchroniser les commandes directement sur ton serveur. Sans cet identifiant, les commandes sont globales et leur apparition peut prendre du temps.

Le bot utilise les logs détaillés, ce qui nécessite deux intents privilégiés : dans le portail développeur, section **Bot**, active **Server Members Intent** et **Message Content Intent**, sinon le bot refusera de se connecter.

La musique nécessite **ffmpeg** installé sur la machine qui héberge le bot (binaire système, pas un paquet Python) :

```sh
# Debian/Ubuntu
sudo apt install -y ffmpeg
```

Sous Windows, télécharge ffmpeg et ajoute son dossier `bin` au PATH.

## Commandes

| Commande | Fonction | Permission du modérateur |
| --- | --- | --- |
| `/config journal:#logs antispam:True` | Choisir le journal et activer l’antispam | Gérer le serveur |
| `/kick membre raison` | Expulser | Expulser des membres |
| `/ban membre raison` | Bannir sans effacer l’historique | Bannir des membres |
| `/unban identifiant raison` | Débannir par identifiant | Bannir des membres |
| `/timeout membre minutes raison` | Timeout de 1 minute à 28 jours ; 0 pour retirer | Exclure temporairement |
| `/clear nombre` | Examiner les derniers 1 à 100 messages et supprimer ceux admissibles | Gérer les messages |
| `/warn membre raison` | Ajouter un avertissement | Exclure temporairement |
| `/warnings membre` | Voir les 5 derniers avertissements | Exclure temporairement |
| `/delwarn numero` | Retirer un avertissement | Exclure temporairement |

### Jeux

| Commande | Fonction |
| --- | --- |
| `/pfc choix` | Pierre-papier-ciseaux contre le bot |
| `/pile pari` | Pile ou face, pari facultatif |
| `/deviner nombre` | Deviner un nombre secret entre 1 et 20 |
| `/quiz` | Question de culture générale, premier clic correct gagne (30 s) |

### Collection de cartes

| Commande | Fonction |
| --- | --- |
| `/quotidien` | Récupérer 20 à 40 pièces, une fois par 24 h |
| `/solde` | Voir son solde de pièces |
| `/ouvrir` | Ouvrir un paquet (40 pièces) et tirer une carte aléatoire selon sa rareté |
| `/cartes [membre]` | Voir sa collection ou celle d’un autre membre |
| `/echanger membre ma_carte sa_carte` | Proposer un échange 1 contre 1 ; l’autre membre accepte ou refuse via des boutons (5 min) |

Le catalogue de cartes (16 cartes, 4 raretés) est défini dans `cards.py` — modifiable librement. Les identifiants de carte (`braise`, `lune`, `phenix`, etc.) s’obtiennent via `/cartes`.

### Musique

| Commande | Fonction |
| --- | --- |
| `/jouer recherche` | Rechercher sur YouTube ou coller un lien ; rejoint ton salon vocal |
| `/pause` / `/reprendre` | Mettre en pause / reprendre |
| `/suivant` | Passer à la musique suivante de la file |
| `/stop` | Vider la file et quitter le salon vocal |
| `/file` | Voir la musique en cours et la file d’attente |

Le bot ne peut jouer que dans un seul salon vocal à la fois par serveur. La récupération dépend de YouTube via `yt-dlp` : une musique introuvable ou un échec d’extraction peuvent survenir après une mise à jour de YouTube, il faudra alors mettre à jour `yt-dlp` (`pip install -U yt-dlp`).

### EA SPORTS FC 27

| Commande | Fonction |
| --- | --- |
| `/fc27` | 5 dernières actus officielles (ea.com), triées par date |
| `/sbc` | SBC (Squad Building Challenges) actifs, chacun avec son image |

`/fc27` lit le site officiel ea.com. `/sbc` lit FUT.GG (site non officiel, non affilié à EA) faute d’API publique EA pour les SBC — un changement de mise en page de FUT.GG peut casser cette commande. Les deux mettent en cache leurs résultats 20 minutes pour éviter de solliciter ces sites à chaque appel.

Les réponses aux commandes de modération sont privées pour le modérateur. Les actions du bot sont envoyées dans le journal configuré ; les actions manuelles des autres modérateurs ne sont pas reprises. Réserve l’accès au journal à ton équipe. Si le journal devient inaccessible, l’action reste effectuée et une alerte apparaît dans la console.

L’antispam est désactivé au départ. Une fois activé, 6 messages en moins de 8 secondes, cumulés sur le serveur, entraînent un timeout de 1 minute. Les administrateurs et les membres avec Gérer les messages ou Exclure temporairement sont exemptés. Il ne supprime pas les messages et ne filtre ni les mots ni les liens. Ses compteurs sont remis à zéro au redémarrage.

`/clear` conserve les messages épinglés et ceux de plus de 13 jours ; le total supprimé peut donc être inférieur au nombre demandé. Les suppressions sont définitives. Les avertissements ne déclenchent pas de sanction automatique.

## Mise en service et sauvegarde

Teste d’abord avec un compte de test dont le rôle est inférieur : ajoute/retire un avertissement, applique/retire un timeout, puis vérifie le journal. Vérifie également qu’un membre sans permission ne peut pas utiliser les commandes. Le bot doit rester lancé sur ton ordinateur ou sur un hébergement pour être connecté en continu.

Configuration et avertissements sont enregistrés dans `guardian.sqlite3`, à côté du code. Arrête le bot avant de sauvegarder ce fichier. Conserve `.env` séparément et ne publie pas la base, qui contient les identifiants et motifs de modération. `/delwarn` permet de retirer les avertissements obsolètes. Lance une seule instance avec cette base.

## Vérification locale

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Les tests couvrent les protections de rôles et le seuil antispam. Une vérification réelle des interactions Discord nécessite ton token et un serveur de test.

Références : https://discordpy.readthedocs.io/en/stable/interactions/api.html et https://docs.discord.com/developers/events/gateway

Si ton application existe déjà, renomme-la **Lyra Bot** dans le portail développeur Discord et vérifie le nom du bot dans la section **Bot**. Le nom affiché sur ton serveur peut aussi être défini via son surnom. Le fichier `guardian.sqlite3` conserve son nom pour préserver les données des installations existantes.
