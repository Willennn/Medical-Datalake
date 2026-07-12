// gen_rapport.js — Rapport Data Lake, mise en page identique au modèle EFREI
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  Header, Footer, PageNumber, PageBreak,
} = require("docx");

// --- Charte extraite du rapport modèle ---
const F = "Times New Roman";
const TITRE = "16213E";     // titres de section
const SOUS = "0F3460";      // sous-titres
const GRIS = "777777";      // commentaires sous figures
const ROUGE = "C00000";     // emplacements à remplir

// Corps de texte : justifié, retrait 1re ligne, 12pt (sz 24)
const p = (t) => new Paragraph({
  alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 140, line: 276 },
  indent: { firstLine: 480 },
  children: [new TextRun({ text: t, font: F, size: 24 })],
});

// Paragraphe sans retrait
const pn = (t) => new Paragraph({
  alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 140, line: 276 },
  children: [new TextRun({ text: t, font: F, size: 24 })],
});

// Puce
const b = (t, gras = null) => new Paragraph({
  bullet: { level: 0 },
  spacing: { after: 90, line: 276 },
  children: gras
    ? [new TextRun({ text: gras, bold: true, font: F, size: 24 }),
       new TextRun({ text: t, font: F, size: 24 })]
    : [new TextRun({ text: t, font: F, size: 24 })],
});

// Commentaire sous figure (gris, italique, 9.5pt — comme le modèle)
const com = (t) => new Paragraph({
  alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 200 },
  children: [new TextRun({ text: t, font: F, size: 19, color: GRIS, italics: true })],
});

// Emplacement de capture
const cap = (t) => new Paragraph({
  spacing: { before: 120, after: 180 },
  alignment: AlignmentType.CENTER,
  shading: { type: ShadingType.CLEAR, fill: "FDECEA" },
  border: {
    top: { style: BorderStyle.SINGLE, size: 6, color: ROUGE },
    bottom: { style: BorderStyle.SINGLE, size: 6, color: ROUGE },
    left: { style: BorderStyle.SINGLE, size: 6, color: ROUGE },
    right: { style: BorderStyle.SINGLE, size: 6, color: ROUGE },
  },
  children: [new TextRun({ text: t, bold: true, italics: true, color: ROUGE, font: F, size: 22 })],
});

// Titres
const h1 = (t) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 360, after: 200 },
  children: [new TextRun({ text: t, bold: true, color: TITRE, font: F, size: 36 })],
});
const h2 = (t) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 240, after: 140 },
  children: [new TextRun({ text: t, bold: true, color: SOUS, font: F, size: 28 })],
});

// Bloc de code / sortie console (Consolas, comme le modèle)
const code = (lignes) => lignes.map((l) => new Paragraph({
  spacing: { after: 0 },
  children: [new TextRun({ text: l, font: "Consolas", size: 19, color: "1A1A2E" })],
}));

// --- En-tête identique au modèle ---
const header = new Header({
  children: [new Table({
    columnWidths: [3200, 3200, 3200],
    width: { size: 9600, type: WidthType.DXA },
    rows: [new TableRow({
      children: [
        new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: "Data Lakes & Data Integration", font: F, size: 20 })] })] }),
        new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: "Projet Final", font: F, size: 20 })] })] }),
        new TableCell({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "EFREI", bold: true, font: F, size: 20, color: SOUS })] })] }),
      ],
    })],
  })],
});

const footer = new Footer({
  children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: [PageNumber.CURRENT], font: F, size: 20, color: GRIS })],
  })],
});

// --- Tableau identité (page de garde) ---
const identite = () => {
  const c = (t, g = false) => new TableCell({
    width: { size: 3200, type: WidthType.DXA },
    margins: { top: 100, bottom: 100, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text: t, bold: g, font: F, size: 24 })] })],
  });
  return new Table({
    columnWidths: [3200, 3200, 3200],
    width: { size: 9600, type: WidthType.DXA },
    rows: [
      new TableRow({ children: [c("Etudiant :", true), c("Professeur :", true), c("Date :", true)] }),
      new TableRow({ children: [c("[VOTRE NOM]"), c("Yvann VINCENT"), c("[DATE]")] }),
    ],
  });
};

// --- Tableau générique ---
const tab = (entetes, lignes, largeurs) => {
  const th = (t, w) => new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: TITRE },
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    children: [new Paragraph({ children: [new TextRun({ text: t, bold: true, color: "FFFFFF", font: F, size: 21 })] })],
  });
  const td = (t, w) => new TableCell({
    width: { size: w, type: WidthType.DXA },
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    children: [new Paragraph({ children: [new TextRun({ text: t, font: F, size: 21 })] })],
  });
  return new Table({
    columnWidths: largeurs,
    width: { size: largeurs.reduce((a, x) => a + x, 0), type: WidthType.DXA },
    rows: [
      new TableRow({ tableHeader: true, children: entetes.map((t, i) => th(t, largeurs[i])) }),
      ...lignes.map((l) => new TableRow({ children: l.map((t, i) => td(t, largeurs[i])) })),
    ],
  });
};

const K = [];

// ================== PAGE DE GARDE ==================
K.push(new Paragraph({ spacing: { before: 1600 }, children: [] }));
K.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 140 },
  children: [new TextRun({ text: "Un data lake peut-il avaler n'importe quel signal vital ?", bold: true, color: TITRE, font: F, size: 44 })],
}));
K.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 500 },
  children: [new TextRun({ text: "Un projet de Data Engineering appliqué aux signaux physiologiques", italics: true, color: GRIS, font: F, size: 26 })],
}));
K.push(cap("[ INSÉRER UNE IMAGE DE COUVERTURE — un tracé ECG/EEG stylisé, ou le schéma d'architecture ]"));
K.push(new Paragraph({ spacing: { before: 900 }, children: [] }));
K.push(identite());
K.push(new Paragraph({ children: [new PageBreak()] }));

// ================== 0. LANCEMENT ==================
K.push(h1("0. Comment lancer ce projet"));
K.push(pn("Ce projet se lance intégralement avec Docker. Trois éléments composent le rendu : l'infrastructure du data lake (entrepôt, base, orchestrateur), une API qui expose les données, et un dashboard qui permet de les explorer visuellement."));

K.push(h2("Prérequis"));
K.push(b("Docker Desktop, pour lancer les services.", "Docker — "));
K.push(b("Python 3.10 ou supérieur, pour le code du pipeline.", "Python — "));
K.push(b("gratuite, à créer sur explore.openaq.org/register, puis à coller dans le fichier .env.", "Une clé API OpenAQ — "));

K.push(h2("Lancement"));
K.push(pn("Dans un terminal ouvert à la racine du projet :"));
K.push(...code([
  "copy .env.example .env          (puis y coller la clé OpenAQ)",
  "docker-compose up -d            (entrepôt + base + Airflow)",
  "pip install -r requirements.txt",
  "",
  "python -m src.storage.minio_client     (crée les buckets)",
  "python -m src.ingestion.ingest_ecg     (ECG : zone raw)",
  "python -m src.pipelines.run_ecg        (ECG : zone staging)",
  "python -m src.models.train_ecg         (ECG : modèle + curated)",
  "python -m src.ingestion.ingest_air     (API : zone raw)",
  "python -m src.pipelines.run_air        (API : zone staging)",
  "python -m src.ingestion.ingest_eeg     (EEG : ~170 Mo, patienter)",
  "python -m src.pipelines.run_eeg        (EEG : zone staging)",
  "python -m src.models.train_eeg         (EEG : modèle + curated)",
]));
K.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
K.push(pn("Puis, dans deux terminaux distincts :"));
K.push(...code([
  "uvicorn src.api.main:app                    -> http://localhost:8000/docs",
  "streamlit run src/dashboard/dashboard.py    -> http://localhost:8501",
]));
K.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
K.push(pn("Airflow est accessible sur http://localhost:8080 (identifiants : airflow / airflow). Il permet de rejouer les trois pipelines automatiquement, sans lancer les commandes à la main."));
K.push(com("Le README du dépôt reprend ces étapes en détail, avec les erreurs courantes et leurs solutions."));

// ================== 1. POURQUOI ==================
K.push(h1("1. Pourquoi ce sujet"));
K.push(p("Nous avons choisi de construire un data lake sur des signaux physiologiques médicaux plutôt que sur un jeu de données générique, pour une raison précise : c'est un domaine où les données sont réellement hétérogènes. Un tracé cardiaque, un enregistrement cérébral à vingt-trois électrodes et un flux d'API n'ont ni le même format, ni la même fréquence, ni le même volume. C'est exactement le type de désordre qu'un data lake est censé savoir absorber."));
K.push(p("Notre objectif n'était donc pas seulement de faire fonctionner un pipeline, mais de vérifier une hypothèse d'architecture : peut-on écrire une chaîne de traitement unique, capable d'accueillir un nouveau domaine sans être réécrite ?"));

K.push(h2("1.1 La question que nous nous posons"));
K.push(p("Concrètement : à partir de signaux médicaux bruts, peut-on construire une plateforme qui les ingère, les transforme, leur applique un modèle et les expose — et qui reste extensible ? Nous nous intéressons autant à la robustesse de l'architecture qu'à la performance des modèles. Et, comme on le verra, ces deux résultats seront très différents."));

K.push(h2("1.2 Les sources de données"));
K.push(pn("Le sujet impose deux sources : un dataset fichier et une source issue d'une API. Nous en avons finalement branché trois."));
K.push(b("MIT-BIH Arrhythmia Database (PhysioNet). Un signal cardiaque continu à 360 Hz, annoté battement par battement par des cardiologues. Trois enregistrements, soit 6 322 battements.", "Source fichier — ECG : "));
K.push(b("CHB-MIT Scalp EEG Database (PhysioNet). Vingt-trois électrodes posées sur le crâne d'un enfant épileptique, à 256 Hz, avec l'horaire exact de chaque crise. Quatre enregistrements, soit 168 Mo et 2 880 fenêtres d'analyse.", "Source fichier — EEG : "));
K.push(b("OpenAQ. La qualité de l'air autour de Paris, en temps réel — un facteur de risque cardio-respiratoire reconnu. Ingérée automatiquement toutes les heures.", "Source API : "));
K.push(p("Ces trois sources sont volontairement incompatibles entre elles. C'était le test : si notre architecture les absorbe sans se déformer, elle est bonne."));

K.push(h2("1.3 Un choix de méthode : mesurer honnêtement"));
K.push(p("Un point que nous considérons comme essentiel, et qui a façonné toutes nos conclusions : nous avons refusé les mesures flatteuses. Pour l'EEG, nous testons le modèle sur un enregistrement qu'il n'a jamais vu, et non sur un découpage aléatoire des données. Un découpage au hasard aurait placé des fenêtres voisines — donc quasi identiques — à la fois dans l'entraînement et dans le test, et nos scores auraient bondi artificiellement. C'est l'équivalent de réviser un examen avec le corrigé sous les yeux."));

// ================== 2. ARCHITECTURE ==================
K.push(h1("2. L'architecture que nous avons construite"));

K.push(h2("2.1 Les trois zones"));
K.push(pn("Nous avons retenu la structure raw / staging / curated proposée en cours, chaque zone correspondant à un état de raffinement."));
K.push(tab(
  ["Zone", "Rôle", "Technologie"],
  [
    ["raw", "Stocke les fichiers exactement tels que reçus, sans aucune modification", "MinIO (S3)"],
    ["staging", "Transforme le signal brut en caractéristiques exploitables", "MinIO (Parquet)"],
    ["curated", "Données propres enrichies de la prédiction du modèle", "PostgreSQL"],
    ["serving", "Expose le lake au monde extérieur", "FastAPI + Streamlit"],
  ],
  [1900, 5300, 2400]
));
K.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
K.push(p("La règle absolue de la zone raw est de ne jamais toucher à l'original. Si nous découvrons demain une erreur dans notre traitement, nous pouvons tout recalculer depuis la source. C'est ce qui distingue un data lake d'un simple dossier de fichiers transformés."));
K.push(cap("[ INSÉRER LE SCHÉMA D'ARCHITECTURE — les trois zones et le flux des données ]"));

K.push(h2("2.2 Les choix techniques et leurs raisons"));
K.push(b("un « S3 maison », gratuit, conforme à la contrainte du sujet, et capable de stocker aussi bien des fichiers binaires que des payloads JSON.", "MinIO — "));
K.push(b("base relationnelle robuste, adaptée à des résultats structurés (une ligne = un événement analysé).", "PostgreSQL — "));
K.push(b("la référence mondiale du traitement de signaux cérébraux (filtrage, lecture des fichiers .edf).", "MNE-Python — "));
K.push(b("l'orchestrateur. Nous l'avons préféré à DVC car il permet le scheduling, indispensable pour ingérer notre source API à intervalle régulier.", "Apache Airflow — "));
K.push(b("pour l'API Gateway : moderne, documenté automatiquement, et supportant l'asynchrone (utile pour le niveau avancé).", "FastAPI — "));
K.push(b("pour le dashboard, écrit en Python pur : aucun code web à maintenir.", "Streamlit — "));

K.push(h2("2.3 Le pattern « processeur enfichable » : le cœur du projet"));
K.push(p("C'est notre décision d'architecture la plus structurante. Plutôt que d'écrire un programme pour l'ECG puis un autre pour l'EEG, nous avons défini un contrat unique — une classe abstraite SignalProcessor — qui décrit la logique commune du pipeline une seule fois. Chaque domaine ne fournit que deux méthodes : comment lire son signal, et quelles caractéristiques en extraire."));
K.push(...code([
  "SignalProcessor        <- écrit UNE fois, partagé par tous",
  "  |- load_raw()        <- « comment lis-tu ton signal ? »   à remplir",
  "  |- to_features()     <- « qu'en extrais-tu ? »            à remplir",
  "  |- run()             <- l'enchaînement complet            DÉJÀ ÉCRIT",
  "",
  "ECGProcessor  ->  découpe par battement, mesure les intervalles",
  "EEGProcessor  ->  filtre, découpe en fenêtres, mesure les fréquences",
  "AirProcessor  ->  aplatit le JSON reçu de l'API",
]));
K.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
K.push(p("Le bénéfice s'est vérifié concrètement au moment d'ajouter l'EEG. Il nous a fallu cinq fichiers nouveaux (lecture, ingestion, transformation, modèle, DAG), et aucune réécriture de l'entrepôt, de l'API ou de l'orchestrateur."));
K.push(p("Soyons toutefois précis, car il serait malhonnête de prétendre que rien n'a bougé : la table finale a dû être étendue — les colonnes de l'EEG n'existaient pas — et l'API a dû apprendre à les renvoyer. Nous l'avons fait par migration, sans détruire les données ECG déjà présentes. C'est le prix normal d'un nouveau domaine, et il est resté faible."));

// ================== 3. PIPELINE ==================
K.push(h1("3. Le pipeline d'intégration"));
K.push(p("Nous avons implémenté trois DAGs Airflow, un par source. Chacun enchaîne les mêmes étapes : ingestion vers la zone raw, transformation vers staging, puis chargement en curated."));

K.push(h2("3.1 Un choix différencié de planification"));
K.push(p("Les DAGs ECG et EEG ne sont pas planifiés : les datasets sont statiques, il serait absurde de les retélécharger périodiquement. Ils se déclenchent à la demande. En revanche, le DAG de la qualité de l'air est planifié toutes les heures, puisque l'API renvoie des mesures en temps réel. Chaque exécution crée un instantané horodaté, sans écraser les précédents : nous construisons ainsi un historique."));
K.push(cap("[ INSÉRER CAPTURE — un DAG affiché en vert dans l'interface Airflow ]"));

K.push(h2("3.2 XCom : faire communiquer les tâches"));
K.push(p("Dans le DAG de la qualité de l'air, la tâche d'ingestion transmet à la tâche suivante, via XCom, l'identifiant de l'instantané qu'elle vient de créer. Sans ce mécanisme, la seconde tâche devrait deviner quel fichier traiter, ou relister l'ensemble du bucket. C'est une petite chose, mais elle illustre bien comment Airflow fait circuler l'information entre étapes."));

// ================== 4. ECG ==================
K.push(h1("4. Premier domaine : le cœur (ECG)"));

K.push(h2("4.1 Transformer un tracé en chiffres"));
K.push(p("Un signal cardiaque brut n'est qu'une longue suite de valeurs, inexploitable telle quelle. Nous le découpons battement par battement — en nous appuyant sur les annotations des cardiologues — et mesurons pour chacun le rythme (le temps écoulé depuis le battement précédent et jusqu'au suivant) ainsi que l'amplitude du pic. Un battement qui arrive trop tôt est suspect : c'est la signature d'une extrasystole."));
K.push(cap("[ INSÉRER CAPTURE — la sortie terminal de run_ecg : nombre de battements par patient ]"));

K.push(h2("4.2 Le déséquilibre, et une découverte inattendue"));
K.push(p("Nos trois enregistrements totalisent 6 322 battements, dont 2 126 anormaux, soit 33,6 %. Ce chiffre nous semblait cohérent — jusqu'à ce que nous regardions patient par patient."));
K.push(tab(
  ["Enregistrement", "Battements", "Anormaux", "Proportion"],
  [
    ["100", "2 273", "34", "1,5 %"],
    ["101", "1 865", "5", "0,3 %"],
    ["102", "2 187", "2 088", "95,5 %"],
  ],
  [2600, 2300, 2300, 2400]
));
K.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
K.push(p("Le patient 102 présente 95 % de battements anormaux, quand les deux autres en ont moins de 2 %. En vérifiant, nous avons compris : il porte un stimulateur cardiaque, ce qui rend la quasi-totalité de ses battements « non normaux » au sens de la classification médicale."));
K.push(p("La conséquence est directe : notre taux global de 33,6 % est un artefact de ce seul patient. Il ne décrit aucun patient réel. Nous ne l'aurions jamais vu sans examiner les enregistrements un par un — et c'est un réflexe que nous avons conservé pour la suite du projet."));

K.push(h2("4.3 Le modèle et son évaluation"));
K.push(p("Nous entraînons une forêt aléatoire pondérée (class_weight = balanced), et nous la comparons systématiquement à une baseline naïve qui répond toujours la classe majoritaire. Sans ce point de comparaison, n'importe quel score peut sembler impressionnant alors qu'il ne bat même pas le hasard structurel des données."));
K.push(tab(
  ["Modèle", "Accuracy", "Rappel (anomalies)", "Précision"],
  [
    ["Baseline naïve", "66,4 %", "0,0 %", "0,0 %"],
    ["Random Forest pondéré", "90,9 %", "85,3 %", "87,5 %"],
  ],
  [3000, 2200, 2500, 1900]
));
K.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
K.push(com("La baseline atteint 66 % d'accuracy sans détecter la moindre anomalie : son rappel est nul. C'est exactement le piège que nous voulions éviter. Notre modèle, lui, retrouve 85 % des battements pathologiques."));
K.push(cap("[ INSÉRER CAPTURE — matrice de confusion et importance des features (sortie de train_ecg) ]"));
K.push(p("Un détail nous a marqués : quatre caractéristiques élémentaires suffisent à atteindre 85 % de rappel. Nous n'avons pas eu besoin d'un réseau de neurones. La qualité de ce qu'on donne au modèle compte davantage que la sophistication du modèle lui-même."));

// ================== 5. EEG ==================
K.push(h1("5. Second domaine : le cerveau (EEG)"));
K.push(p("C'est ici que le projet devient réellement instructif — parce que c'est ici que notre modèle échoue, et que nous avons compris pourquoi."));

K.push(h2("5.1 Ce que nous mesurons : les bandes de fréquence"));
K.push(p("Le cerveau produit des ondes électriques à différentes fréquences, que les neurologues regroupent en cinq bandes (delta, theta, alpha, beta, gamma). Pendant une crise d'épilepsie, les neurones se déchargent de façon synchrone et anormale, et la répartition de l'énergie entre ces bandes change."));
K.push(p("Nous filtrons donc le signal entre 0,5 et 45 Hz avec MNE-Python, le découpons en fenêtres de cinq secondes, et calculons pour chacune la part d'énergie dans chaque bande."));

K.push(h2("5.2 Un déséquilibre bien plus violent"));
K.push(p("Nos quatre enregistrements totalisent 2 880 fenêtres, dont 44 seulement correspondent à une crise — soit 1,53 %. Une baseline qui répondrait « jamais de crise » obtiendrait donc déjà 98,5 % d'accuracy sans rien détecter du tout."));
K.push(com("Cette seule phrase résume pourquoi l'accuracy est inutilisable sur ce problème."));

K.push(h2("5.3 Le sur-apprentissage, pris en flagrant délit"));
K.push(p("C'est notre découverte la plus parlante, et elle mérite d'être racontée précisément."));
K.push(p("En consultant notre dashboard, nous avons d'abord été satisfaits : sur les enregistrements chb01_03, chb01_04 et chb01_16, le modèle retrouve la quasi-totalité des fenêtres de crise, presque sans fausse alerte. Il avait l'air excellent."));
K.push(p("Sauf que ce sont précisément les trois enregistrements sur lesquels il s'est entraîné. Il les avait déjà vus. Lui demander de les reconnaître revient à faire passer un examen à un élève en lui laissant le corrigé sous les yeux."));
K.push(p("Sur chb01_18 — le seul qu'il n'a jamais vu — il ne retrouve plus que 3 fenêtres de crise sur 18."));
K.push(tab(
  ["Enregistrement", "Rôle", "Fenêtres de crise retrouvées"],
  [
    ["chb01_03, 04, 16", "Entraînement (déjà vus)", "quasi toutes"],
    ["chb01_18", "Test (jamais vu)", "3 sur 18, soit 16,7 %"],
  ],
  [3000, 3200, 3400]
));
K.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
K.push(p("C'est la définition même du sur-apprentissage : le modèle a mémorisé au lieu de comprendre. Si nous avions regardé les scores globaux sans distinguer entraînement et test, nous aurions conclu que notre détecteur fonctionnait — et nous aurions eu tort."));
K.push(cap("[ INSÉRER CAPTURE — la page EEG du dashboard, avec les bandeaux « entraînement » et « vrai test » ]"));

K.push(h2("5.4 Les résultats, sans les embellir"));
K.push(tab(
  ["Modèle", "Accuracy", "Rappel (crises)", "Gain réel"],
  [
    ["Baseline naïve", "97,5 %", "0,0 %", "—"],
    ["Random Forest pondéré", "97,8 %", "16,7 %", "+0,3 point d'accuracy"],
  ],
  [3000, 2000, 2300, 2300]
));
K.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
K.push(p("Notre modèle affiche 97,8 % d'accuracy. Le chiffre est magnifique et ne veut rien dire : une baseline qui ne détecte rien atteint 97,5 %. Notre apport réel est de 0,3 point. Sur des données déséquilibrées, l'accuracy est un mensonge poli."));
K.push(p("Une nuance en faveur du modèle, tout de même : en observant la courbe de probabilité, on voit qu'il sent la crise passer — sa confiance monte nettement au bon moment. Il ne reste simplement pas assez longtemps au-dessus du seuil de décision. Un système d'alerte réel, avec un seuil abaissé, déclencherait peut-être quand même. Mais trois fenêtres sur dix-huit, c'est trop fragile pour que nous prétendions le contraire."));

K.push(h2("5.5 Pourquoi il échoue : nous avons trop écrasé le signal"));
K.push(p("En analysant l'importance des caractéristiques, nous avons fait un constat désagréable. Le modèle s'appuie à 47 % sur l'amplitude brute du signal — c'est-à-dire sur « le signal est-il fort ? », une information grossière — tandis que la puissance dans la bande delta, que nous avions soigneusement calculée, ne pèse que 5 %."));
K.push(p("La raison tient à notre propre traitement. En passant de 168 Mo à 0,57 Mo de caractéristiques, nous n'avons pas « retiré du bruit » : nous avons jeté de l'information. Concrètement, nous moyennons les vingt-trois canaux en un seul. Or une crise d'épilepsie démarre dans une zone précise du cerveau : si trois électrodes s'affolent et que vingt restent calmes, la moyenne bouge à peine. Nous diluons le signal par vingt-trois."));
K.push(p("Nous avons donc détruit exactement l'information dont le modèle avait besoin. C'est notre erreur la plus instructive, et elle ne se voit pas dans le code : elle se voit dans les résultats."));

// ================== 6. API ==================
K.push(h1("6. L'API Gateway"));
K.push(p("L'API offre une interface simple pour récupérer les données du lake sans manipuler directement l'entrepôt ou la base. Notre dashboard, notamment, ne parle jamais à PostgreSQL : il passe exclusivement par l'API. Si nous changions de base de données, il n'aurait pas une ligne à modifier."));
K.push(tab(
  ["Endpoint", "Rôle"],
  [
    ["GET /health", "Vérifie que MinIO et PostgreSQL répondent"],
    ["GET /raw", "Liste les fichiers bruts de la zone raw"],
    ["GET /staging", "Liste les fichiers de caractéristiques"],
    ["GET /curated", "Renvoie les analyses et les prédictions du modèle"],
    ["GET /stats", "Métriques de remplissage des buckets et de la base"],
    ["POST /ingest", "Niveau avancé : ingestion de données JSON"],
    ["POST /ingest_fast", "Niveau avancé : version optimisée"],
  ],
  [3000, 6600]
));
K.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
K.push(cap("[ INSÉRER CAPTURES — la page /docs de l'API, et les réponses de /health et /stats ]"));

K.push(h2("6.1 La robustesse : un endpoint de monitoring qui plante ne sert à rien"));
K.push(p("En testant notre API, nous avons découvert que l'endpoint /stats plantait si l'un des deux services était éteint. C'est un contresens : c'est précisément lorsqu'un service tombe qu'on a besoin de le savoir. Nous l'avons rendu tolérant aux pannes — il renvoie désormais les informations disponibles, accompagnées d'un champ d'erreur explicite pour ce qui manque."));

// ================== 7. NIVEAU AVANCE ==================
K.push(h1("7. Niveau avancé : /ingest et /ingest_fast"));

K.push(h2("7.1 Notre approche"));
K.push(p("Nous avons volontairement écrit /ingest de façon naïve — non pas absurde, mais telle qu'un développeur l'écrit spontanément sans penser à la performance. Trois choses le ralentissent : le modèle est rechargé depuis le disque à chaque appel, les éléments sont traités un par un dans une boucle Python, et chaque élément donne lieu à sa propre requête d'insertion."));
K.push(pn("La version optimisée corrige ces trois points :"));
K.push(b("le modèle est chargé une seule fois puis conservé en mémoire.", "Mise en cache — "));
K.push(b("NumPy calcule les caractéristiques de tout le lot d'un coup, et le modèle prédit sur l'ensemble en un seul appel.", "Vectorisation — "));
K.push(b("les cent insertions sont regroupées en une seule requête, donc un seul aller-retour vers la base.", "Insertion groupée — "));
K.push(p("Nous tenons à préciser que nous n'avons pas ralenti /ingest artificiellement pour gonfler le gain. Les deux endpoints font exactement le même travail ; seule la manière change."));

K.push(h2("7.2 Les résultats mesurés"));
K.push(pn("Méthode : moyenne sur cinq essais, après deux appels de préchauffage."));
K.push(tab(
  ["Taille du lot", "/ingest", "/ingest_fast", "Gain"],
  [
    ["1 élément", "123,53 ms", "163,56 ms", "− 32,4 %"],
    ["100 éléments", "4 608,97 ms", "169,56 ms", "+ 96,3 %  (27× plus rapide)"],
  ],
  [2300, 2200, 2300, 2800]
));
K.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
K.push(cap("[ INSÉRER CAPTURE — le tableau récapitulatif produit par le script de benchmark ]"));

K.push(h2("7.3 Le résultat que nous n'attendions pas"));
K.push(p("Sur un lot de cent éléments, l'objectif de 30 % est largement dépassé : nous atteignons 96,3 %, soit un facteur 27. Mais sur un lot d'un seul élément, notre gain est négatif : la version « optimisée » est 32 % plus lente que la naïve."));
K.push(p("Ce n'est pas un échec, c'est une leçon. Nos trois optimisations sont des optimisations de lot. Sur un élément unique, elles ajoutent le coût de leur machinerie sans jamais en tirer le bénéfice : vectoriser un tableau d'une ligne n'apporte rien, et regrouper une seule insertion revient à faire une seule insertion. Le temps est alors dominé par des frais fixes — la latence du réseau, l'ouverture de la connexion — que la vectorisation ne touche pas."));
K.push(p("Une optimisation n'est donc jamais bonne dans l'absolu. Elle est bonne pour un régime d'utilisation donné. Nous préférons présenter ce résultat en l'état plutôt que de masquer la mesure gênante."));

// ================== 8. DASHBOARD ==================
K.push(h1("8. Le dashboard"));
K.push(p("Nous avons construit un dashboard Streamlit en six pages, qui expose non seulement les données mais aussi notre démarche : le problème posé, l'architecture, l'état réel du lake, les deux domaines médicaux, et nos conclusions. Il consomme exclusivement l'API."));
K.push(p("C'est en le construisant que nous avons découvert le sur-apprentissage décrit en section 5.3 : en visualisant enregistrement par enregistrement, l'écart entre les données d'entraînement et le test nous a sauté aux yeux — ce que les métriques agrégées masquaient."));
K.push(cap("[ INSÉRER CAPTURES du dashboard — la vue d'ensemble du lake, la page ECG, la page EEG ]"));

// ================== 9. LIMITES ==================
K.push(h1("9. Ce que notre projet ne fait pas"));
K.push(p("Nous préférons énoncer clairement nos limites plutôt que de présenter le projet comme abouti."));
K.push(b("il détecte les crises trop mal pour un usage clinique. Nous l'assumons et nous en expliquons les causes plutôt que de le maquiller derrière une accuracy flatteuse.", "Le modèle EEG n'est pas utilisable — "));
K.push(b("nous n'avons utilisé qu'un seul patient EEG et trois patients ECG. Rien ne garantit que nos résultats se généralisent à d'autres.", "Peu de données — "));
K.push(b("nous avons ingéré la qualité de l'air, mais nous ne l'avons pas encore reliée aux signaux physiologiques. Le lake est prêt pour cette analyse ; nous ne l'avons pas menée.", "Les sources ne sont pas croisées — "));
K.push(b("nous avons vérifié notre code à la main. Un projet de production disposerait d'une suite de tests s'exécutant à chaque modification.", "Aucun test automatisé — "));
K.push(b("entraîner un modèle écrase le précédent. Il faudrait conserver un historique pour pouvoir revenir en arrière.", "Pas de versionnage des modèles — "));

// ================== 10. CONCLUSION ==================
K.push(h1("10. Ce que nous retenons"));
K.push(p("Le résultat le plus formateur de ce projet n'est pas celui que nous attendions."));
K.push(p("Notre architecture a tenu : ajouter l'EEG, un signal à vingt-trois canaux dans un format totalement différent, nous a demandé cinq fichiers et aucune réécriture de l'infrastructure. Notre endpoint optimisé est vingt-sept fois plus rapide que sa version naïve. Notre modèle ECG retrouve 85 % des battements pathologiques avec quatre caractéristiques élémentaires."));
K.push(p("Et pourtant, le même pipeline, appliqué à l'EEG, produit un modèle qui retrouve seulement 17 % des fenêtres de crise sur des données qu'il n'a jamais vues. Même code, même architecture, même type de modèle — résultats opposés."));
K.push(p("La leçon est là : la difficulté ne venait pas du code, mais des données, et surtout de ce que nous en avions fait. En moyennant vingt-trois électrodes en une seule valeur, nous avons détruit l'information qui permet de localiser une crise. Aucune élégance d'architecture ne compense un mauvais choix de représentation."));
K.push(p("Nous retenons également deux réflexes que nous n'avions pas au départ : ne jamais faire confiance à une accuracy sur des données déséquilibrées, et toujours regarder la distribution avant la moyenne — c'est en examinant les patients un par un que nous avons compris que notre taux global d'anomalies cardiaques ne décrivait personne."));
K.push(p("Si nous devions poursuivre, nous ne toucherions pas aux réglages du modèle : nous changerions d'approche. Conserver les vingt-trois canaux séparés, entraîner un réseau de neurones sur des spectrogrammes complets, et abaisser le seuil de décision — car en médecine, une fausse alerte coûte bien moins cher qu'une crise manquée."));

// ================== ANNEXES ==================
K.push(h1("Annexes"));
K.push(b("[ INSÉRER LE LIEN ]", "Dépôt GitHub : "));
K.push(b("MIT-BIH Arrhythmia Database et CHB-MIT Scalp EEG Database (PhysioNet), API OpenAQ v3.", "Sources de données : "));
K.push(b("ARCHITECTURE.md (les choix techniques), SPECS.md (la feuille de route), GUIDE.md (le rôle de chaque fichier), README.md (l'installation).", "Documentation du dépôt : "));

// --- Assemblage ---
const doc = new Document({
  creator: "Projet Data Lake",
  title: "Rapport — Data Lake médical",
  styles: { default: { document: { run: { font: F, size: 24 } } } },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 } } },  // A4
    headers: { default: header },
    footers: { default: footer },
    children: K,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("Rapport_DataLake_Medical.docx", buf);
  console.log("✅ Rapport généré.");
});
