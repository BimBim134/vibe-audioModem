# Vibe AudioModem — Manuel { #top }

Vibe AudioModem envoie de courts messages texte par l'**audio** d'une radio et les décode tout près du plancher de bruit. La liaison est à sens unique : pas de voie de retour, pas d'accusé de réception, pas de nouvel essai. Il est fait pour les radioamateurs, d'abord en FM VHF et UHF, entre quelques stations d'un même groupe.

Appuyez sur **F1** dans l'application pour ouvrir ce manuel à tout moment.

## Sommaire { #contents }

1. [Fonctionnement](#how-it-works)
2. [Installer et démarrer](#install)
3. [La page](#page)
4. [Brancher une radio](#radio)
5. [Envoyer un message](#send)
6. [Recevoir](#receive)
7. [Réglages](#settings)
8. [Le PTT avec Hamlib](#ptt)
9. [Lead-in et TX blanking](#lead-in-blanking)
10. [Historique et export CSV](#history)
11. [Réceptions gardées (débogage)](#stored)
12. [Quitter](#quit)
13. [Problèmes](#problems)
14. [Vocabulaire](#words)

## Fonctionnement { #how-it-works }

Un **Message** est découpé en **Fragments** d'au plus 17 octets. Chaque Fragment est envoyé dans sa propre **Trame** : un **Préambule** que le récepteur reconnaît, puis les données, protégées par un code correcteur d'erreurs (un turbo-code) et un CRC. Le son est fait de huit tonalités (8-FSK) ; le **Preset** fixe la durée de chaque symbole.

| Preset | Symbole | Une Trame dure | Largeur du Signal | Lit jusqu'à environ |
| :-- | --: | --: | --: | --: |
| Lent – Portée maximale | 320 ms | 54 s | 29 Hz | −22 dB |
| Standard | 80 ms | 14 s | 107 Hz | −16 dB |
| Rapide – Bonnes conditions | 40 ms | 7 s | 212 Hz | −13 dB |

La dernière colonne est le rapport signal sur bruit, dans une bande de bruit de 2 500 Hz, auquel au moins 95 % des Messages arrivent dans les simulations du banc d'essai. Un canal réel est moins bon qu'un canal simulé : comptez quelques dB de moins. Un Preset lent porte plus loin et dure plus longtemps ; un Preset rapide demande un canal plus propre.

Le Signal reste toujours entre 300 et 2 700 Hz, la bande audio d'une radio BLU ou FM. La tonalité la plus basse est à **1 450 Hz**, sauf si vous choisissez une autre fréquence.

## Installer et démarrer { #install }

**Windows.** Téléchargez l'archive de la dernière version, décompressez-la et lancez `VibeModem.exe`. La page s'ouvre dans votre navigateur. L'application n'est pas signée : si Windows SmartScreen annonce un éditeur inconnu, choisissez *Informations complémentaires*, puis *Exécuter quand même*.

**macOS.** Décompressez l'archive. macOS bloque une application non signée : faites un clic droit sur l'application et choisissez *Ouvrir*, ou retirez l'indicateur de quarantaine dans un terminal avec `xattr -dr com.apple.quarantine VibeModem.app`. Ce paquet n'a été vérifié que par des tests automatiques ; il n'a pas été essayé à la main sur un Mac.

**Linux.** Il n'y a pas encore de paquet. À partir d'une copie des sources, avec [uv](https://docs.astral.sh/uv/) installé :

```bash
uv sync --locked --all-extras
uv run python -m vibemodem.app
```

L'application tourne sur votre ordinateur seulement et sert sa page sur `127.0.0.1` : rien n'est accessible depuis le réseau. Appuyez sur **Ctrl+C** dans le terminal, ou sur le bouton marche/arrêt de la page, pour l'arrêter.

## La page { #page }

- **Barre du haut.** L'état de l'écoute, **Listen** / **Stop listening**, **Settings**, **Manual** (aussi F1) et le bouton marche/arrêt, qui quitte l'application.
- **Spectre et cascade.** Ce qu'entend la carte son, de 300 à 2 700 Hz. La cascade montre la dernière minute, le plus récent en haut. Un Signal apparaît comme une ligne brillante.
- **Conversation.** Les Messages envoyés (à droite) et reçus (à gauche), dans l'ordre du temps, avec la façon dont chacun a été reçu. Au-dessus : les filtres et le lien **Export CSV**.
- **Zone d'envoi.** La fréquence d'émission, le texte, **Send** et, pendant l'envoi, **Cancel**.

## Brancher une radio { #radio }

Il faut un chemin audio dans les deux sens entre l'ordinateur et la radio : une interface audio (une carte son USB, ou une interface faite pour la radioamateur comme le Digirig), ou la carte son de l'ordinateur avec des câbles.

1. La **sortie** de l'ordinateur va à l'**entrée micro ou données** de la radio. L'**entrée** de l'ordinateur vient du **haut-parleur ou de la sortie données** de la radio.
2. Dans **Settings → General → Audio device**, choisissez l'entrée et la sortie, puis **Apply**. La carte son doit accepter 48 000 Hz, un canal.
3. Réglez les niveaux. À l'émission, montez le volume jusqu'à une modulation normale sur la radio, **pas plus** : un Signal saturé s'étale sur d'autres fréquences et se lit moins bien. À la réception, le spectre doit montrer le bruit nettement sans remplir toute la fenêtre.
4. Choisissez comment la radio est commandée : par son **VOX**, ou par le **PTT** de Hamlib (voir [plus bas](#ptt)).

Essayez d'abord sur une charge fictive, ou avec deux radios proches l'une de l'autre, à faible puissance et dans le cadre de votre licence.

## Envoyer un message { #send }

1. Écrivez le texte. La ligne dessous indique le nombre de Fragments et la durée à l'antenne.
2. Si besoin, changez **Send at** : la fréquence de la tonalité la plus basse, dans la plage affichée. Changez-la pour éviter un signal déjà présent.
3. Appuyez sur **Send** (ou Entrée). **Cancel** coupe la Transmission, même au milieu du son.

Un Message trop long pour le Preset est refusé, et la ligne dit quoi faire (un texte plus court, un Preset plus rapide ou moins de répétitions).

Avec **Repetitions** au-dessus de 1, chaque Fragment est envoyé plusieurs fois, dans un ordre différent à chaque fois. Cela coûte du temps d'antenne et aide quand des Trames sont perdues.

Si un Signal est en train d'arriver, une ligne le dit et **Send** devient **Send anyway**. C'est seulement un avertissement : sur un canal partagé, attendez la fin de l'autre station, mais rien ne vous empêche d'envoyer.

## Recevoir { #receive }

Appuyez sur **Listen**. L'application écoute l'entrée, trouve les Préambules et décode les Trames. Le Preset doit être celui de l'autre station : il se choisit dans les réglages et ne peut pas changer pendant l'écoute.

- Un Message apparaît quand tous ses Fragments sont lus. Il montre sa fréquence et son SNR.
- Un Message dont seuls certains Fragments ont été lus s'affiche **incomplete**, avec les parties lues et les Fragments manquants.
- **Receiving a signal at … Hz** signifie qu'un Préambule a été entendu et que la Trame arrive encore.
- Un Signal trouvé mais illisible s'affiche **not decoded** (une ligne grise). Décochez **Not decoded** pour les masquer.
- **Signals from … to … Hz** masque ce qui est hors d'une plage de fréquences.

À l'arrêt de l'écoute, une dernière passe décode ce qui a été entendu.

## Réglages { #settings }

Ouvrez **Settings**. **Apply** est nécessaire pour le Preset et les appareils. Les autres réglages agissent dès que vous les changez. Tous sont gardés d'une session à l'autre dans `settings.json`. Le Preset et les appareils ne peuvent pas changer pendant l'envoi ou l'écoute ; les autres le peuvent.

### General

| Réglage | Défaut | Ce qu'il fait |
| :-- | :-- | :-- |
| **Callsign** | aucun | Votre indicatif, 3 à 12 lettres et chiffres, écrit en majuscules. Il est écrit devant chaque Message envoyé : `F4JBO: hello`. Ajoutez `/P` quand vous opérez en portable (`F4JBO/P`). L'historique le garde. Le préfixe compte dans les 17 octets d'un Fragment. |
| **Audio device — Input / Output** | par défaut | La carte son utilisée. Un appareil absent au démarrage suivant est ignoré et gardé pour son retour. |
| **Preset** | Standard | Voir [Fonctionnement](#how-it-works). L'autre station doit utiliser le même. |
| **Repetitions** | 1 (de 1 à 8) | Combien de fois le Message est envoyé. |

### Advanced

| Réglage | Défaut | Ce qu'il fait |
| :-- | :-- | :-- |
| **Listening band — From / To** | vide | Seuls les Signaux **entièrement dans** cette bande sont lus. Servez-vous-en pour écarter le bruit basse fréquence d'une radio, ou pour choisir la partie de l'audio où se tient la conversation. Elle agit à la passe suivante, même pendant l'écoute. Vide : tout. Elle n'est pas gardée d'une session à l'autre. |
| **Lead-in — Length** | 0 ms (0 à 5 000) | Une tonalité avant le Préambule. Voir [Lead-in](#lead-in-blanking). |
| **Push to talk** | désactivé | Commande la radio par Hamlib. Voir [PTT](#ptt). |
| **TX blanking — Margin** | 250 ms (0 à 10 000) | Silence après votre propre Transmission. Voir [TX blanking](#lead-in-blanking). |
| **Stored receptions** | désactivé, 200 Mo | Voir [Réceptions gardées](#stored). |

### History

**Clear the history** efface tous les Messages gardés, après un second clic de confirmation. Voir [Historique](#history).

## Le PTT avec Hamlib { #ptt }

Avec un **VOX**, la radio se déclenche d'elle-même quand elle entend du son ; laissez **Push to talk** désactivé. Sinon, l'application demande à **Hamlib** de commander la radio. Elle parle à **`rigctld`**, un petit programme de Hamlib que vous lancez pour votre radio. `rigctld` peut commander une radio par son contrôle CAT, ou une ligne série (RTS ou DTR) comme celle d'un Digirig.

**Installer Hamlib.**

- Linux : `sudo apt install libhamlib-utils` (Debian et Ubuntu) ; le paquet porte un autre nom sur d'autres distributions.
- macOS : `brew install hamlib`.
- Windows : téléchargez la version Windows de Hamlib sur le site du projet et décompressez-la ; `rigctld.exe` est dans son dossier `bin`.

**Lancer `rigctld`** dans un terminal, et le laisser tourner. `rigctl -l` liste les modèles de radio et leurs numéros. Exemples, à adapter à votre radio et à votre port :

```bash
rigctld -m 1                                   # une radio factice, pour essayer sans radio
rigctld -m <modèle> -r /dev/ttyUSB0 -s 9600    # une radio avec contrôle CAT
rigctld -m <modèle> -P RTS -p /dev/ttyUSB0     # commander la ligne RTS d'un port série
```

Vérifiez avec `rigctl -m 2 -r localhost:4532 T 1` puis `... T 0` que la radio part bien en émission, avant d'utiliser l'application. Ces commandes dépendent de votre radio et de votre interface ; consultez la documentation de Hamlib pour la vôtre.

**Dans l'application**, ouvrez **Settings → Advanced → Push to talk**, cochez **Key the radio through rigctld**, et donnez l'adresse (`127.0.0.1` quand `rigctld` tourne sur cet ordinateur) et le port (`4532`, le défaut de `rigctld`). Les deux délais sont le temps entre la mise en émission et le premier son, et entre le dernier son et le retour en réception (100 ms chacun par défaut). Allongez-les si le début ou la fin de vos Messages est coupé.

La radio est mise en émission **avant** le Lead-in et relâchée après la fin du son, **même** si la carte son tombe en panne ou si vous annulez. Si `rigctld` est injoignable, rien n'est joué, le Message s'affiche en échec et la raison est écrite sur la page.

## Lead-in et TX blanking { #lead-in-blanking }

**Lead-in.** Une tonalité simple, à la fréquence de la tonalité la plus basse, envoyée avant le Préambule. Elle laisse à un **squelch** qui s'ouvre tard, ou à un **VOX** qui coupe le début du son, le temps de s'ouvrir avant le début du Préambule. Il est désactivé par défaut ; essayez 300 à 500 ms. Sa durée compte dans le temps d'antenne affiché, et le récepteur l'ignore. Au banc d'essai, il n'a modifié ni la réception ni les fausses alarmes.

**TX blanking.** Quand votre station émet, son propre son revient par l'interface audio. Le récepteur l'ignore : votre propre Transmission n'est donc jamais affichée comme reçue. Vos Messages restent dans la conversation comme **envoyés**. L'entrée est sourde du début de l'émission jusqu'à la fin du son, plus le délai de la carte son, plus la **Margin** (250 ms par défaut). Augmentez la Margin si votre radio a une longue queue de squelch. Diminuez-la si une station répond tout de suite et que vous perdez le début de son Préambule. Le TX blanking est toujours actif.

## Historique et export CSV { #history }

Chaque Message, envoyé ou reçu, est écrit dans `history.sqlite3`, dans le dossier de données de l'application, au moment où il se produit, et réaffiché au démarrage de l'application (les 1 000 derniers). Seuls le texte et les valeurs sont gardés, jamais le son. Le fichier reste sur votre ordinateur.

Chaque ligne contient l'heure, le sens, l'indicatif de l'émetteur, le texte, la fréquence, le SNR, le Preset et l'état (*complete* ou *incomplete* pour ce qui est reçu ; *sent*, *cancelled* ou *failed* pour ce qui est envoyé). L'indicatif est lu dans le préfixe `CALLSIGN: `, `/P` compris.

**Export CSV** (au-dessus de la conversation) télécharge tout l'historique dans un fichier pour tableur : UTF-8 avec marque d'ordre des octets, colonnes séparées par `;` (il s'ouvre correctement dans un tableur en français), heure en UTC. Un texte qui commence par `=`, `+`, `-` ou `@` reçoit une apostrophe devant, pour qu'un tableur ne l'exécute jamais comme une formule.

**Clear the history** (Settings → General) vide le fichier et la conversation.

## Réceptions gardées (débogage) { #stored }

Pour le débogage, chaque réception peut être gardée sous forme d'un fichier son de 3 secondes autour de chaque Signal, et d'un fichier des valeurs de la réception. C'est désactivé par défaut. Cochez **Keep the audio and the figures of what is received** et fixez une limite en Mo ; les plus anciennes sont supprimées en premier quand la limite est atteinte. **Delete all stored receptions** vide le dossier.

Elles sont dans le dossier de données de l'application, à côté de l'historique et des réglages :

| Système | Dossier |
| :-- | :-- |
| Linux | `~/.local/share/vibemodem/receptions` |
| macOS | `~/Library/Application Support/VibeModem/receptions` |
| Windows | `%LOCALAPPDATA%\VibeModem\receptions` |

L'option `--receptions-dir <dossier>` choisit un autre dossier quand l'application est lancée depuis un terminal.

## Quitter { #quit }

Utilisez le bouton marche/arrêt (en haut à droite) et cliquez une seconde fois pour confirmer. Si l'application écoute encore, elle le dit : quitter arrête l'écoute. **Fermer l'onglet du navigateur n'arrête pas l'application** : elle continue d'écouter et d'envoyer. Depuis un terminal, **Ctrl+C** l'arrête proprement.

## Problèmes { #problems }

| Ce que vous voyez | Ce qu'il faut faire |
| :-- | :-- |
| *the … device cannot be opened at 48000 Hz in mono* | Choisissez un autre appareil, ou réglez la carte son sur 48 000 Hz. |
| Aucun appareil dans les listes | Branchez l'interface et redémarrez l'application. |
| *Stop listening and sending to change these* | Le Preset et les appareils ne peuvent pas changer pendant l'écoute ou l'envoi. |
| Un Message est refusé car trop long | Raccourcissez-le, choisissez un Preset plus rapide ou diminuez les Repetitions. |
| Rien n'est reçu | Vérifiez que les deux stations ont le même Preset, que le niveau est bon (le spectre bouge), que la **Listening band** est vide ou contient le Signal, et la fréquence de l'autre station. |
| Un Message est reçu incomplet | Demandez une nouvelle Transmission ; utilisez plus de Repetitions ; allongez les délais de votre PTT. |
| *PTT: cannot talk to rigctld…* | Lancez `rigctld`, vérifiez l'adresse et le port, puis réessayez. |
| Le début des Messages est coupé à l'antenne | Ajoutez un Lead-in, ou un délai plus long avant le son (PTT). |
| History not written | L'erreur s'affiche sur la page ; vérifiez que le dossier de données est accessible en écriture. |

## Vocabulaire { #words }

- **Message** : le texte que vous envoyez, jusqu'à quelques kilo-octets.
- **Fragment** : un morceau de Message, au plus 17 octets, envoyé dans une Trame.
- **Trame** (*Frame*) : le son d'un Fragment : un Préambule et les données codées.
- **Transmission** : tout ce que la station envoie pour un Message, avec ses répétitions.
- **Préambule** (*Preamble*) : la partie d'une Trame que le récepteur reconnaît.
- **Signal** : ce que le récepteur trouve dans l'audio : une Trame, lisible ou non.
- **Preset** : Portée maximale, Standard ou Rapide ; la vitesse des symboles.
- **Tonalité la plus basse** (*Lowest tone*) : la plus basse des huit tonalités d'un Signal ; la fréquence à laquelle vous choisissez d'émettre.
- **Listening band** : la partie de l'audio où le récepteur cherche des Signaux.
- **Lead-in** : une tonalité facultative avant le Préambule.
- **TX blanking** : le récepteur qui ignore le son de la station elle-même.
- **Callsign** : votre indicatif, écrit devant vos Messages.
