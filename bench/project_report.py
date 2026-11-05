"""Build the report of the whole project, for a talk: docs/measurements/project-report.html.

    python -m bench.project_report

One self-contained page (in French): the goal, how the modem works, the application, the journey
ticket by ticket, the measurements with their charts, and the real-world trials. Numbers are read
from the result files of `docs/measurements/`; the explanations are written below.
"""

import html
import json
from pathlib import Path

from bench import cable_report as cable
from bench.cable_report import MEASUREMENTS, PRESETS

OUTPUT = MEASUREMENTS / "project-report.html"
CODES = [
    ("baseline-modem.json", "Convolutionnel (référence)"),
    ("ldpc-modem.json", "LDPC"),
    ("turbo-modem.json", "Turbo (retenu)"),
    ("long-convolutional-modem.json", "Convolutionnel long (WSPR)"),
]
RUN_LABELS = {
    "1-fast": "Essai 1, pas de 2 dB",
    "1-standard": "Essai 1, pas de 2 dB",
    "1-max-range": "Essai 1, pas de 2 dB",
    "2-max-range": "Essai 2, pas de 1 dB",
    "3-max-range": "Essai 3, enregistrement continu",
    "4-max-range": "Essai 4, en direct",
    "4b-max-range": "Essai 4, même audio décodé hors ligne",
}


def code_runs() -> list[dict]:
    runs = []
    for name, label in CODES:
        saved = json.loads((MEASUREMENTS / name).read_text())
        levels = [[p["snr_db"], p["successes"], p["trials"]] for p in saved["curve"] if -18 <= p["snr_db"] <= -14]
        runs.append({"label": label, "levels": levels})
    return runs


def french_runs() -> dict[str, list[dict]]:
    runs = [dict(r, label=RUN_LABELS.get(r["id"], r["label"])) for r in cable.load_runs()]
    return {p: [r for r in runs if r["preset"] == p] for p in PRESETS}


def pipeline() -> str:
    """The chain from text to Message, as boxes and arrows."""
    boxes = [
        ("Texte", "le Message", 0, 0),
        ("Fragments", "17 o + 3 d'en-tête", 1, 0),
        ("Frame", "200 bits, CRC-32", 2, 0),
        ("Code turbo", "200 → 412 bits", 3, 0),
        ("Entrelacement", "bits dispersés", 4, 0),
        ("8-FSK", "3 bits / symbole", 5, 0),
        ("Recherche Preamble", "tout temps et ton", 5, 1),
        ("Valeurs souples", "énergie des tons", 4, 1),
        ("Décodage turbo", "8 itérations", 3, 1),
        ("Contrôle CRC-32", "rejet au moindre doute", 2, 1),
        ("Réassemblage", "ordre, copies", 1, 1),
        ("Message", "ou incomplet", 0, 1),
    ]
    w, h, gx, gy = 128, 56, 12, 86
    out = [f'<svg viewBox="0 0 {6 * (w + gx)} {2 * gy + 8}" role="img" aria-label="Chaîne d\'émission et de réception">']
    out.append('<defs><marker id="ar" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
               '<path d="M0,0 L6,3 L0,6" fill="none" stroke="var(--muted)"/></marker></defs>')
    for index, (title, sub, col, row) in enumerate(boxes):
        x, y = col * (w + gx) + 2, row * gy + 14
        # sender runs left to right, receiver right to left
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="box{" rx" if row else ""}"/>')
        out.append(f'<text x="{x + w / 2}" y="{y + 24}" text-anchor="middle" class="bt">{html.escape(title)}</text>')
        out.append(f'<text x="{x + w / 2}" y="{y + 40}" text-anchor="middle" class="bs">{html.escape(sub)}</text>')
        if index < 5:
            out.append(f'<line x1="{x + w}" y1="{y + h / 2}" x2="{x + w + gx - 2}" y2="{y + h / 2}" class="ar"/>')
        elif index == 5:
            out.append(f'<line x1="{x + w / 2}" y1="{y + h}" x2="{x + w / 2}" y2="{y + gy - 2}" class="ar"/>')
        elif index > 6:
            out.append(f'<line x1="{x + w + gx - 2}" y1="{y + h / 2}" x2="{x + w}" y2="{y + h / 2}" class="ar"/>')
        elif index == 6:
            out.append(f'<line x1="{x}" y1="{y + h / 2}" x2="{x - gx + 2}" y2="{y + h / 2}" class="ar"/>')
    out.append(f'<text x="4" y="10" class="bs">ÉMISSION</text><text x="4" y="{gy + 10}" class="bs">RÉCEPTION</text>')
    out.append("</svg>")
    return "".join(out)


def presets_table() -> str:
    rows = []
    facts = {
        "max-range": ("320 ms", "29 Hz", "54,4 s", "561 octets", "−22 dB", "−16 dB"),
        "standard": ("80 ms", "107 Hz", "13,6 s", "2 244 octets", "−16 dB", "−8 dB"),
        "fast": ("40 ms", "212 Hz", "6,8 s", "4 335 octets", "−13 dB", "90 % à 0 dB seulement"),
    }
    for name in ("max-range", "standard", "fast"):
        rows.append(f"<tr><td class='name'><strong>{name}</strong></td>" + "".join(f"<td>{v}</td>" for v in facts[name]) + "</tr>")
    return (
        "<div class='scroll'><table><tr><th class='name'>Preset</th><th>Symbole</th><th>Bande à −20 dB</th>"
        "<th>Durée d'une Frame</th><th>Plus gros Message (1 copie)</th><th>Seuil, bruit blanc</th>"
        "<th>Seuil, fading HF</th></tr>" + "".join(rows) + "</table></div>"
    )


TIMELINE = [
    ("#2", "Fondations", "Squelette du dépôt, outillage (uv, Python 3.12), intégration continue sur Linux, Windows et macOS."),
    ("#3", "Paquetage", "Un « hello » installable par un non-développeur sous Windows et macOS : on a vérifié la faisabilité avant de construire."),
    ("#4", "Simulateur de canal", "Bruit blanc à un SNR exact, décalage de fréquence, dérive d'horloge, écrêtage, impulsions, fading de Rayleigh, filtre SSB. Tout est reproductible par graine."),
    ("#5", "Mesure du seuil", "L'interface commune des modems candidats et la commande qui calcule le Success threshold. Un modem jouet (BPSK) a servi à vérifier que le banc retrouve la courbe théorique."),
    ("#6", "Modem de référence", "8-FSK, code convolutif de contrainte 7, décodage de Viterbi à valeurs souples, CRC-32 : seuil <strong>−15 dB</strong>."),
    ("#7–#9", "Trois autres codes", "Interface « Code » à valeurs souples, puis LDPC (−15,5 dB), turbo (−16 dB) et convolutif long du WSPR décodé par Fano (−15,5 dB)."),
    ("#10", "Choix du code", "Le turbo gagne : meilleur sur bruit blanc et nettement devant sous fading (ADR 0003). Les trois autres restent dans le dépôt."),
    ("#11", "Largeur de bande et balayage M-FSK", "16 combinaisons de tons et de durées de symbole, entrelaceur, répétition. 8 tons est le meilleur compromis."),
    ("#12", "Candidat GFSK", "Le GFSK à faible débit, pour la comparaison : au moins 2,5 dB derrière le M-FSK à énergie et bande égales. Son code a été retiré (historique git)."),
    ("#13", "Les trois Presets", "max-range, standard, fast : seule la durée du symbole change (ADR 0004)."),
    ("#14", "Protocole de Message", "Fragments, CRC, déduplication, réassemblage, Messages incomplets (ADR 0005)."),
    ("#15", "Durée et taille", "Estimation exacte de la durée d'émission et plafond de 30 minutes, avec un refus expliqué."),
    ("#16", "Couche audio", "Cartes son, fichiers WAV, liste des périphériques."),
    ("#17", "Application locale", "Page web servie localement : écrire, envoyer, écouter, lire."),
    ("#18", "Spectre et qualité", "Spectre et cascade, SNR et décalage estimés, Signaux trouvés mais non lus, taux de fausses alarmes mesuré."),
    ("#19", "Presets dans l'interface", "Choix du Preset et durée affichée avant l'envoi."),
    ("#20", "Réceptions gardées", "L'audio de chaque Frame est conservé avec ses indicateurs, et rejoué à l'identique sur le banc (ADR 0006)."),
    ("#21", "Validation sur câble", "Les trois Presets sur une vraie chaîne audio, à des SNR connus : voir plus bas."),
    ("#24–#26", "Page et conversation", "Page découpée en fichiers, filtres de la conversation, avertissement quand on quitte en écoutant."),
    ("#28", "Écart de max-range", "Jusqu'à 3 à 4 dB perdus sur câble en max-range selon l'essai, et un récepteur en direct qui lit moins que le décodage hors ligne : cause encore à l'étude."),
]

OPEN = [
    ("#22", "Installateur Windows", "à faire"),
    ("#23", "Campagne sur le terrain : haut-parleur et micro, puis radios", "à faire"),
    ("#27", "Choisir la plage de fréquences d'entrée", "à cadrer"),
    ("#28", "Écart de max-range sur câble", "en cours"),
    ("#1", "La spécification d'ensemble, qui se ferme quand v1 est complète", "ouvert"),
]

STYLE_EXTRA = """
svg .box { fill:var(--panel); stroke:var(--grid); } svg .box.rx { fill:var(--bg); stroke:var(--s1); }
svg .bt { fill:var(--fg); font-size:12px; font-weight:600; } svg .bs { fill:var(--muted); font-size:10.5px; }
svg .ar { stroke:var(--muted); stroke-width:1.5; marker-end:url(#ar); }
.big { display:grid; grid-template-columns:repeat(auto-fit,minmax(9rem,1fr)); gap:.75rem; margin:1rem 0; }
.big div { background:var(--panel); border-radius:8px; padding:.7rem .9rem; }
.big b { display:block; font-size:1.6rem; } .big span { color:var(--muted); font-size:.85rem; }
.tl td:first-child { text-align:left; white-space:nowrap; font-weight:600; } .tl td { text-align:left; vertical-align:top; }
.tl th { text-align:left; }
nav { background:var(--panel); border-radius:8px; padding:.6rem 1rem; font-size:.95rem; } nav a { margin-right:1rem; }
"""


def part(title: str, body: str, anchor: str) -> str:
    return f'<h2 id="{anchor}">{title}</h2>{body}'


def build() -> str:
    runs = french_runs()
    page = []
    page.append(
        '<div class="big">'
        "<div><b>−22 dB</b><span>SNR de réception (bande de 2 500 Hz) en max-range, dans 29 Hz de bande</span></div>"
        "<div><b>3 Presets</b><span>de 6,8 s à 54 s par Frame</span></div>"
        "<div><b>~1 070</b><span>tests automatiques</span></div>"
        "<div><b>0</b><span>faux Message accepté, sur toutes les mesures</span></div></div>"
    )
    page.append(
        '<nav><a href="#but">But</a><a href="#fonctionnement">Fonctionnement</a><a href="#presets">Presets</a>'
        '<a href="#application">Application</a><a href="#parcours">Parcours</a><a href="#mesures">Mesures</a>'
        '<a href="#terrain">Essais réels</a><a href="#suite">Suite</a><a href="#lexique">Lexique</a></nav>'
    )
    page.append(part("1. Le but", """
<p>Les radioamateurs qui veulent échanger de courts messages sur des liaisons HF ou VHF faibles n'ont pas
d'outil simple qui travaille près du plancher de bruit, dans une bande étroite, à sens unique, et qu'un
opérateur non technicien puisse installer. Le prototype de départ (GMSK à 200 bauds, bâti sur GNU Radio, six
processus qui s'envoient des messages) occupait trop de bande, corrigeait les erreurs avec des décisions dures
et était fragile à installer. Il est gelé sous le tag <code>legacy-v0</code> : on le lit pour ses idées, on ne le
corrige pas (ADR 0001).</p>
<p>Le projet est donc <strong>une réécriture complète</strong> : un modem qui envoie un Message dans un canal
audio (la bande passante d'un émetteur-récepteur BLU) et le décode au plus près du bruit, dans environ
100 Hz, <strong>sans voie de retour</strong>. L'opérateur l'installe sans terminal, ouvre une page locale,
choisit un Preset, écrit son texte, voit la durée d'émission et envoie. Il est « terminé » quand un message
tapé sur une machine arrive intact sur une seconde, d'abord par une boucle audio virtuelle, puis sur une vraie
chaîne audio (spécification : ticket #1).</p>
<h3>Une mesure qui sert de règle : le Success threshold</h3>
<p>Pour comparer objectivement deux modems, on mesure le <strong>seuil de réussite</strong> : le plus faible
rapport signal sur bruit, évalué dans une bande de référence de 2 500 Hz, auquel au moins 95 % des Messages
d'essai sont reçus corrects. Plus il est bas (−16 dB, −22 dB…), plus le modem entend loin dans le bruit. À
−16 dB, le signal est 40 fois moins puissant que le bruit de la bande de référence. Tout le projet est mené
à la mesure : chaque choix (modulation, code, durée du symbole) est tranché par un chiffre, et le chiffre est
consigné avec la décision.</p>
""", "but"))
    page.append(part("2. Comment ça marche", f"""
<h3>La chaîne complète</h3>
{pipeline()}
<h3>À l'émission</h3>
<ol>
<li><strong>Fragments.</strong> Le texte est découpé en morceaux de 17 octets au plus. Chacun reçoit trois octets
d'en-tête : l'identifiant du Message, son numéro, le nombre total de Fragments. Un Message peut compter jusqu'à
255 Fragments (4 335 octets).</li>
<li><strong>Frame.</strong> Un Fragment devient une Frame : un octet de longueur, le Fragment complété, un
<strong>CRC-32</strong> (somme de contrôle sur 32 bits), puis un « blanchiment » qui évite les motifs réguliers.
L'ensemble fait 200 bits. La Frame est l'unité la plus petite que le récepteur puisse vérifier seul.</li>
<li><strong>Code correcteur turbo.</strong> Les 200 bits deviennent 412 bits codés : deux codes convolutifs
récursifs à 8 états, travaillant sur les mêmes bits dans un ordre mélangé par un entrelaceur interne, dont on
garde la moitié de la redondance. Le récepteur pourra réparer des bits abîmés par le bruit.</li>
<li><strong>Entrelacement.</strong> Les bits codés sont dispersés sur toute la durée de la Frame : un
évanouissement ou une impulsion abîme des bits éparpillés, que le code sait réparer, plutôt qu'un bloc
entier, qu'il ne saurait pas réparer.</li>
<li><strong>Modulation 8-FSK.</strong> On émet, à chaque symbole, <em>un seul ton parmi huit</em>. Trois bits
choisissent le ton ; 412 bits font 138 symboles. Les tons sont espacés de l'inverse de la durée du symbole
(12,5 Hz pour 80 ms) et la phase est continue, pour ne pas étaler le spectre.</li>
<li><strong>Preamble.</strong> Avant les 138 symboles de données vient une suite connue de 32 symboles : le
<strong>Preamble</strong>. La Frame fait donc 170 symboles. Chaque Frame porte son propre Preamble, donc chacune
peut être trouvée et décodée seule.</li>
<li><strong>Son.</strong> Une onde mono à 48 kHz, placée à la fréquence choisie par l'opérateur (le « ton le plus
bas ») dans la bande audio de la radio. On peut envoyer le tout plusieurs fois (<em>copies</em>), chaque copie
commençant à un autre Fragment pour qu'une même perte ne frappe pas les mêmes morceaux.</li>
</ol>
<h3>À la réception</h3>
<ol>
<li><strong>Recherche du Preamble.</strong> Le récepteur ne sait ni quand l'émission commence, ni à quelle
fréquence elle se trouve : il balaie donc <em>tous les instants et toutes les fréquences</em>. Il calcule
l'énergie de chaque ton dans un spectrogramme, la compare à un plancher de bruit estimé, et cherche la suite
de tons connue du Preamble. Le résultat est un <em>score</em>, en écarts-types au-dessus de ce que donnerait
du bruit seul. Aucune horloge partagée, aucun réglage fin de la radio n'est nécessaire.</li>
<li><strong>Affinage et valeurs souples.</strong> Une fois la Frame localisée (temps et fréquence), on mesure
l'énergie des huit tons à chaque symbole. Au lieu de décider « ce bit vaut 0 », on garde <em>à quel point on
y croit</em> : ce sont les <strong>valeurs souples</strong>. C'est ce qui permet de travailler à −16 dB.</li>
<li><strong>Décodage turbo.</strong> Huit itérations où les deux décodeurs se passent leurs doutes jusqu'à
s'accorder.</li>
<li><strong>Contrôle CRC-32.</strong> Si la somme de contrôle ne passe pas, la Frame est rejetée : le code
turbo répond toujours quelque chose, donc le CRC est la seule barrière contre un faux Message. Elle a tenu sur
toutes les mesures.</li>
<li><strong>Signal non décodé.</strong> Si un Preamble a été trouvé nettement (score d'au moins 10) mais que la
Frame n'a pas passé le CRC, l'opérateur est prévenu qu'un Signal a été entendu et perdu, au lieu de croire à
du silence.</li>
<li><strong>Réassemblage.</strong> Les Fragments valides sont remis dans l'ordre, les copies sont dédoublonnées,
et un Message n'est livré qu'une fois. Si l'écoute se termine avant la fin, le Message est annoncé
<em>incomplet</em>, avec ce qui est arrivé et ce qui manque, sans jamais le présenter comme complet.</li>
</ol>
<h3>Pourquoi ces choix</h3>
<ul>
<li><strong>FSK non cohérent plutôt que phase.</strong> Il ne demande ni synchronisation de la phase ni horloge
précise, et résiste mieux aux évanouissements. C'est ce qui permet de fonctionner à travers une radio quelconque.</li>
<li><strong>8 tons.</strong> À énergie égale, 8 et 16 tons font jeu égal, 4 tons sont 0,5 à 1,5 dB derrière et 2
tons 6 dB derrière ; 8 tons occupe moitié moins de bande que 16.</li>
<li><strong>Un Preamble par Frame.</strong> Il coûte 19 % de durée mais une perte n'abîme que les Frames
touchées, et la dérive d'horloge entre deux cartes son (jusqu'à 90 ms en 30 minutes) est remesurée à chaque
Frame.</li>
<li><strong>Le même signal pour les trois Presets.</strong> On n'a pas trois modems : on a un modem dont la durée
du symbole change. Doubler le symbole gagne 3 dB, double la durée d'émission, et laisse l'énergie émise
inchangée (environ −4,7 dB). Les Presets sont un choix de <em>temps passé à l'antenne</em>, pas de rendement.</li>
</ul>
""", "fonctionnement"))
    page.append(part("3. Les trois Presets", presets_table() + """
<p>Les seuils sont mesurés avec des Messages de 12 octets. Fast ne tient pas le
fading HF à 95 % : 6,8 s sont trop courtes pour traverser les évanouissements, il est fait pour les bons
canaux. Un modem est construit pour un seul Preset ; le récepteur doit savoir lequel écouter.</p>
""", "presets"))
    page.append(part("4. L'application", """
<p>Trois couches strictement séparées : un <strong>cœur</strong> de traitement du signal qui n'a accès à rien
(ni carte son, ni fichier, ni horloge, ni réseau, donc testable sur de simples tableaux), une couche
<strong>io</strong> pour les cartes son et les fichiers WAV, et une couche <strong>app</strong> qui sert une page
web locale (uniquement joignable depuis l'ordinateur lui-même). À côté, un <strong>banc</strong> (simulateur de
canal et outils de mesure) qui n'est pas dans l'application. Pas de GNU Radio (ADR 0002) : NumPy et SciPy
suffisent et l'installation devient simple.</p>
<ul>
<li><strong>Envoyer :</strong> texte, Preset, périphérique de sortie, fréquence du ton le plus bas, nombre de
copies ; la durée est affichée avant l'envoi et un Message trop long est refusé avec une explication et une
suggestion ; l'émission peut être annulée.</li>
<li><strong>Écouter :</strong> périphérique d'entrée, spectre en direct et cascade, avertissement de niveau
trop faible ou d'écrêtage, détection automatique de la fréquence et du début.</li>
<li><strong>Conversation :</strong> ce qui est envoyé et reçu dans une même liste datée, avec le SNR, le
décalage de fréquence et le score de synchronisation de chaque réception ; Messages incomplets et Signaux
perdus signalés ; filtres (de, jusqu'à, seulement les perdus).</li>
<li><strong>Conserver (« Keep »)</strong> : l'audio de chaque Frame (3 secondes autour) et ses indicateurs, pour
le rejouer plus tard dans le décodeur sur le banc, ce qui permet d'ajuster le récepteur avec de vraies
réceptions (ADR 0006).</li>
<li><strong>Sécurité de la page :</strong> uniquement locale, les réglages sont acceptés en entier ou refusés,
l'arrêt est propre, et fermer l'application en écoutant affiche un avertissement orange.</li>
</ul>
""", "application"))
    rows = "".join(f"<tr><td>{t}</td><td class='name'><strong>{html.escape(a)}</strong></td><td>{b}</td></tr>" for t, a, b in TIMELINE)
    page.append(part("5. Le parcours, ticket par ticket", f"""
<p>Le travail a suivi un ordre précis : <em>d'abord le banc de mesure, ensuite les candidats, enfin
l'application, enfin la réalité</em>. On n'a rien décidé sans chiffre, et chaque décision durable a son
<em>Architecture Decision Record</em> (ADR). Les tickets sont des « tranches verticales » : chacune traverse
toutes les couches et se démontre seule.</p>
<div class="scroll"><table class="tl"><tr><th>Ticket</th><th>Sujet</th><th>Ce qui a été fait</th></tr>{rows}</table></div>
<p class="note">Environ 4 000 lignes de code d'application, 2 300 de banc et 6 600 de tests ; les décisions
sont dans <code>docs/adr/</code>, le vocabulaire dans <code>GLOSSARY.md</code>, les mesures dans
<code>docs/measurements/</code>.</p>
""", "parcours"))
    page.append(part("6. Les mesures", f"""
<h3>Quatre codes correcteurs, sur le même modem</h3>
<p>Même modem, mêmes Messages, mêmes graines, 300 Messages par niveau de bruit blanc. Seul le code change.
Seuils à 95 % : <strong>−15 dB</strong> (référence), <strong>−15,5 dB</strong> (LDPC),
<strong>−16 dB</strong> (turbo), <strong>−15,5 dB</strong> (convolutif long). Le turbo gagne 1 dB sur la
référence, soit environ 21 % de puissance en moins pour la même portée.</p>
{cable.chart("fast", code_runs(), [])}
{cable.legend(code_runs(), None)}
<h3>Sur des canaux qui ressemblent à une vraie radio</h3>
<div class="scroll"><table><tr><th class="name">Seuil à 95 %</th><th>Référence</th><th>LDPC</th><th>Turbo</th><th>Convolutif long</th></tr>
<tr><td class="name">bruit filtré SSB</td><td>−14 dB</td><td>−15 dB</td><td><b>−16 dB</b></td><td><b>−16 dB</b></td></tr>
<tr><td class="name">fading HF</td><td>non atteint</td><td>−2 dB</td><td><b>−5 dB</b></td><td>non atteint</td></tr>
<tr><td class="name">« sale » (fading, impulsions, écrêtage, dérive)</td><td>−3 dB</td><td>−2 dB</td><td><b>−5 dB</b></td><td>non atteint</td></tr>
<tr><td class="name">fading HF, 90 % des Messages</td><td>−5,8 dB</td><td>−10,0 dB</td><td><b>−11,5 dB</b></td><td>−7,0 dB</td></tr>
</table></div>
<p>Le convolutif long est le plus raide sur bruit blanc mais perd sous fading : son décodeur séquentiel
abandonne. Le turbo est devant partout (ADR 0003). Il répond toujours quelque chose, donc il compte sur le
CRC-32 ; aucun faux Message n'a été accepté dans toutes les mesures.</p>
<h3>Combien de tons, quelle durée de symbole (turbo, bruit blanc)</h3>
<div class="scroll"><table><tr><th>Tons</th><th>Symbole</th><th>Bande</th><th>Durée</th><th>Seuil 95 %</th><th>Énergie à 95 %</th></tr>
<tr><td>2</td><td>80 ms</td><td>26 Hz</td><td>35 s</td><td>−14 dB</td><td>+1,5 dB</td></tr>
<tr><td>4</td><td>80 ms</td><td>55 Hz</td><td>19 s</td><td>−17 dB</td><td>−4,2 dB</td></tr>
<tr><td><b>8</b></td><td><b>80 ms</b></td><td>124 Hz</td><td>13,6 s</td><td>−16 dB</td><td>−4,7 dB</td></tr>
<tr><td>8</td><td>160 ms</td><td>64 Hz</td><td>27 s</td><td>−19 dB</td><td>−4,7 dB</td></tr>
<tr><td>8</td><td>320 ms</td><td>31 Hz</td><td>54 s</td><td>−22 dB</td><td>−4,6 dB</td></tr>
<tr><td>16</td><td>80 ms</td><td>226 Hz</td><td>10,8 s</td><td>−15 dB</td><td>−4,7 dB</td></tr>
</table></div>
<p>La colonne « énergie » est le seuil plus 10 log<sub>10</sub>(durée) : elle reste à −4,7 dB pour 8 et 16 tons.
Autrement dit, gagner 3 dB en doublant le symbole, c'est seulement émettre deux fois plus longtemps.</p>
<h3>Le GFSK est-il meilleur ? Non</h3>
<p>Le GFSK à faible débit (25 à 100 bauds, plusieurs indices de modulation et filtres gaussiens) a été essayé
avec le même code, la même Frame et le même Preamble. À énergie et bande égales, il est au moins
<strong>2,5 dB derrière</strong> le M-FSK ; le GMSK (indice 0,5, celui du prototype d'origine) est 3 à 4 dB
derrière l'indice 1, parce qu'un récepteur non cohérent ne peut pas exploiter l'écart de tons plus étroit. Son
code a été retiré du dépôt (il reste dans l'historique git) ; les mesures restent.</p>
<h3>Les fausses alarmes</h3>
<p>En 80 heures de bruit seul, <strong>aucun Message</strong> n'a été lu (le CRC tient). Les Signaux « trouvés mais
non lus » sont rapportés à partir d'un score de 10 : le bruit seul ne dépasse jamais 7,7, un Signal au seuil de
réussite ne descend jamais sous 15. Résultat : 0 fausse alarme en 20 heures par Preset à partir de 10.</p>
""", "mesures"))
    summary = cable.summary_table(runs)
    sections = "".join(
        f"<h3>{preset.capitalize()}</h3>{cable.chart(preset, runs[preset], cable.load_simulator(preset))}"
        f"{cable.legend(runs[preset], 'Simulateur (bruit blanc)')}{cable.table(runs[preset])}"
        for preset in PRESETS
    )
    page.append(part("7. Les essais réels", f"""
<h3>Dans une pièce, avec des haut-parleurs et un micro</h3>
<p>Un PC portable émet par ses haut-parleurs vers le micro intégré d'une tour, avec un peu de bruit ambiant. Les
trois Presets fonctionnent, et les Messages courts arrivent tous. Un Message de dix Fragments en fast n'a
retrouvé que cinq Fragments à −5 à −7 dB, soit environ 7 dB de moins que le simulateur, probablement à cause de
la réverbération (non démontré). Cet essai a aussi révélé un défaut : des claquements (touches, haut-parleur)
se faisaient prendre pour un Preamble. Le détecteur compare maintenant chaque symbole au reste des tons et plafonne
chaque contribution (<code>tests/test_clicks.py</code>), sans changer les seuils.</p>
<h3>Sur un câble audio, à des SNR connus</h3>
<p>Le portable ajoute lui-même du bruit blanc à un SNR exact (dans la bande de 2 500 Hz), joue le résultat par sa
carte son et un câble vers une interface audio de la tour, qui fait tourner l'application avec « Keep ». Chaque
Message dit son SNR et son numéro. 20 Messages par niveau (10 en max-range). La campagne a tourné seule, de
bout en bout, par SSH.</p>
{summary}
{sections}
<h3>Ce que ça nous apprend</h3>
<ul>
<li><strong>Fast et standard</strong> atteignent sur câble exactement le seuil du simulateur : 20 sur 20 au seuil,
0 sur 20 deux décibels plus bas. La courbe est une falaise. Les cartes son et le câble ne coûtent rien.</li>
<li><strong>Aucune perte au-dessus du seuil</strong>, aucun trou de capture, et le SNR estimé par le récepteur
est à 0,2 dB de celui imposé.</li>
<li><strong>Max-range</strong> a d'abord perdu 3 à 4 dB (seuil −18 puis −19 dB au lieu de −22 dB), mais cette
perte ne s'est pas reproduite à l'identique : dans les essais suivants tous les Messages sont lus à −21 dB, et à
−22 dB quand on décode hors ligne l'enregistrement continu du câble. Le détecteur, la dérive d'horloge (17 ppm,
environ 1 ms sur 54 s) et le bruit de la carte de réception (−103 dBFS) sont écartés. Il reste deux effets :
une chaîne dont l'état change d'un essai à l'autre, et un récepteur en direct qui lit moins de Messages que le
décodage hors ligne du même enregistrement aux niveaux les plus bas (5 sur 10 contre 10 sur 10 à −22 dB).
Ticket #28.</li>
<li><strong>La pièce coûte, pas la carte son :</strong> les 7 dB perdus dans la pièce en fast sont acoustiques
(haut-parleur, micro, réverbération), pas ceux du modem.</li>
</ul>
""", "terrain"))
    open_rows = "".join(f"<tr><td>{t}</td><td class='name'>{html.escape(a)}</td><td>{b}</td></tr>" for t, a, b in OPEN)
    page.append(part("8. Ce qui reste", f"""
<div class="scroll"><table class="tl"><tr><th>Ticket</th><th>Sujet</th><th>État</th></tr>{open_rows}</table></div>
<ul>
<li>Le <strong>niveau de sortie</strong> du portable n'a pas été testé (100 %, 25 %, 6 %) : on ne règle pas le
volume à distance par SSH.</li>
<li>Les seuils <strong>sur radio réelle</strong> n'ont pas été mesurés : c'est la campagne #23.</li>
<li>Le <strong>Preset est choisi à la main</strong> des deux côtés ; le détecter automatiquement est une
décision à prendre plus tard (ADR 0004).</li>
<li>Pistes d'optimisation notées : Preamble plus court après la première Frame, Frames plus longues,
retransmission des seules Frames manquantes.</li>
</ul>
""", "suite"))
    page.append(part("9. Lexique", """
<div class="scroll"><table class="tl">
<tr><td>Message</td><td>Le texte ou les octets que l'utilisateur veut envoyer.</td></tr>
<tr><td>Fragment</td><td>La tranche d'un Message portée par une Frame (17 octets au plus).</td></tr>
<tr><td>Frame</td><td>La plus petite unité sur l'onde que le récepteur puisse décoder et vérifier seul.</td></tr>
<tr><td>Transmission</td><td>Une émission continue d'un Message, copies comprises.</td></tr>
<tr><td>Copy</td><td>Un envoi supplémentaire de tous les Fragments, démarrant à un autre Fragment.</td></tr>
<tr><td>Preamble</td><td>La suite de symboles connue au début de chaque Frame ; le récepteur la cherche partout.</td></tr>
<tr><td>Signal</td><td>Ce que le récepteur détecte à une fréquence et un instant donnés.</td></tr>
<tr><td>Preset</td><td>Un profil nommé de modulation et de codage : max-range, standard, fast.</td></tr>
<tr><td>Success threshold</td><td>Le plus faible SNR (bande de 2 500 Hz) où 95 % des Messages arrivent corrects.</td></tr>
<tr><td>Valeur souple</td><td>Ce qu'un démodulateur dit d'un bit : le signe dit lequel, la taille dit à quel point on y croit.</td></tr>
<tr><td>Interleaver</td><td>L'étape qui disperse les bits codés pour que les erreurs en rafale deviennent des erreurs éparses.</td></tr>
<tr><td>Kept reception</td><td>Le son d'une Frame et ses indicateurs, conservés pour être rejoués.</td></tr>
<tr><td>Undecoded Signal</td><td>Un Signal trouvé mais dont la Frame n'a pas passé le contrôle.</td></tr>
</table></div>
<p class="note">Régénérer cette page : <code>python -m bench.project_report</code>. Annexe technique en
anglais : <code>docs/measurements/cable-trial/report.html</code>.</p>
""", "lexique"))
    head = (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Vibe AudioModem, rapport du projet</title><style>{cable.STYLE}{STYLE_EXTRA}</style></head><body>"
        "<h1>Vibe AudioModem</h1>"
        "<p class='meta'>Un modem de données à sens unique pour les signaux faibles, réécrit de zéro : "
        "comment il fonctionne, ce qui a été fait, ce qui a été mesuré.</p>"
    )
    return head + "".join(page) + "</body></html>"


def main() -> None:
    OUTPUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
