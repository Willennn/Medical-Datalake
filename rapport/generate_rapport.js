// generate_rapport.js
// Génère un squelette de rapport Word (.docx) pour le projet Data Lake médical.
// Style inspiré d'un rapport académique EFREI : page de titre, en-têtes,
// sections numérotées, ton à la première personne, emplacements à remplir.

const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  Header, Footer, PageNumber, TableOfContents, PageBreak, LevelFormat,
} = require("docx");

// ---------- Palette & constantes ----------
const NAVY = "1F3864";     // bleu foncé pour les titres
const ACCENT = "2E74B5";   // bleu accent pour sous-titres
const PLACEHOLDER = "C00000"; // rouge pour les zones à remplir
const GREY = "808080";
const FONT = "Times New Roman";

// ---------- Helpers de rédaction ----------

// Paragraphe de texte normal (justifié).
function p(text, opts = {}) {
  return new Paragraph({
    alignment: opts.align || AlignmentType.JUSTIFIED,
    spacing: { after: 160, line: 276 },
    children: [new TextRun({ text, font: FONT, size: 22, ...opts })],
  });
}

// Puce de liste.
function bullet(text, boldPart = null) {
  const children = [];
  if (boldPart) {
    children.push(new TextRun({ text: boldPart + " ", bold: true, font: FONT, size: 22 }));
    children.push(new TextRun({ text, font: FONT, size: 22 }));
  } else {
    children.push(new TextRun({ text, font: FONT, size: 22 }));
  }
  return new Paragraph({
    bullet: { level: 0 },
    spacing: { after: 100, line: 276 },
    children,
  });
}

// Emplacement à remplir (rouge, encadré, très visible).
function placeholder(text) {
  return new Paragraph({
    spacing: { before: 120, after: 160 },
    shading: { type: ShadingType.CLEAR, fill: "FDECEA" },
    border: {
      top: { style: BorderStyle.SINGLE, size: 6, color: PLACEHOLDER },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: PLACEHOLDER },
      left: { style: BorderStyle.SINGLE, size: 6, color: PLACEHOLDER },
      right: { style: BorderStyle.SINGLE, size: 6, color: PLACEHOLDER },
    },
    children: [new TextRun({ text: "  " + text, bold: true, italics: true, color: PLACEHOLDER, font: FONT, size: 22 })],
  });
}

// Conseil de rédaction (gris, italique) — à SUPPRIMER une fois la section écrite.
function tip(text) {
  return new Paragraph({
    spacing: { after: 160 },
    children: [new TextRun({ text: "💡 Conseil de rédaction — " + text, italics: true, color: GREY, font: FONT, size: 20 })],
  });
}

// Titre de section (niveau 1).
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 200 },
    children: [new TextRun({ text, bold: true, color: NAVY, font: FONT, size: 32 })],
  });
}

// Sous-titre (niveau 2).
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 140 },
    children: [new TextRun({ text, bold: true, color: ACCENT, font: FONT, size: 26 })],
  });
}

// ---------- En-tête et pied de page ----------
const header = new Header({
  children: [new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" } },
    children: [
      new TextRun({ text: "Data Lakes & Data Integration", font: FONT, size: 18, color: GREY }),
      new TextRun({ text: "\t\tProjet Final — EFREI 2025-2026", font: FONT, size: 18, color: GREY }),
    ],
  })],
});

const footer = new Footer({
  children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: ["Page ", PageNumber.CURRENT, " / ", PageNumber.TOTAL_PAGES], font: FONT, size: 18, color: GREY })],
  })],
});

// ---------- Petit tableau d'identité (page de titre) ----------
function identityTable() {
  const cell = (txt, bold = false) => new TableCell({
    width: { size: 3120, type: WidthType.DXA },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text: txt, bold, font: FONT, size: 22 })] })],
  });
  return new Table({
    columnWidths: [3120, 3120, 3120],
    width: { size: 9360, type: WidthType.DXA },
    rows: [
      new TableRow({ children: [cell("Étudiant :", true), cell("Professeur :", true), cell("Date :", true)] }),
      new TableRow({ children: [cell("[VOTRE NOM]"), cell("Yvann VINCENT"), cell("[DATE DE RENDU]")] }),
    ],
  });
}

// ---------- Tableau des endpoints de l'API ----------
function endpointsTable() {
  const hdr = (t) => new TableCell({
    width: { size: 4680, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: NAVY },
    margins: { top: 60, bottom: 60, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text: t, bold: true, color: "FFFFFF", font: FONT, size: 20 })] })],
  });
  const cell = (t, mono = false) => new TableCell({
    width: { size: 4680, type: WidthType.DXA },
    margins: { top: 60, bottom: 60, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text: t, font: mono ? "Consolas" : FONT, size: 20 })] })],
  });
  const rows = [
    ["GET /health", "Vérifie que les services (MinIO, PostgreSQL) répondent"],
    ["GET /raw", "Liste / récupère les données brutes de la zone raw"],
    ["GET /staging", "Récupère les features intermédiaires"],
    ["GET /curated", "Récupère les résultats finaux + prédictions du modèle"],
    ["GET /stats", "Métriques : nb de fichiers, taille des buckets, nb de lignes"],
    ["POST /ingest", "(Avancé) Ingère des données JSON dans le pipeline"],
    ["POST /ingest_fast", "(Avancé) Version optimisée, > 30 % plus rapide"],
  ];
  return new Table({
    columnWidths: [4680, 4680],
    width: { size: 9360, type: WidthType.DXA },
    rows: [
      new TableRow({ tableHeader: true, children: [hdr("Endpoint"), hdr("Rôle")] }),
      ...rows.map(([a, b]) => new TableRow({ children: [cell(a, true), cell(b)] })),
    ],
  });
}

// ---------- Tableau de résultats de perf (à compléter) ----------
function perfTable() {
  const hdr = (t) => new TableCell({
    width: { size: 2340, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: NAVY },
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ children: [new TextRun({ text: t, bold: true, color: "FFFFFF", font: FONT, size: 20 })] })],
  });
  const cell = (t, ph = false) => new TableCell({
    width: { size: 2340, type: WidthType.DXA },
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ children: [new TextRun({ text: t, font: FONT, size: 20, color: ph ? PLACEHOLDER : "000000", italics: ph })] })],
  });
  return new Table({
    columnWidths: [2340, 2340, 2340, 2340],
    width: { size: 9360, type: WidthType.DXA },
    rows: [
      new TableRow({ tableHeader: true, children: [hdr("Taille du batch"), hdr("/ingest (ms)"), hdr("/ingest_fast (ms)"), hdr("Gain (%)")] }),
      new TableRow({ children: [cell("1 élément"), cell("[…]", true), cell("[…]", true), cell("[…]", true)] }),
      new TableRow({ children: [cell("100 éléments"), cell("[…]", true), cell("[…]", true), cell("[…]", true)] }),
    ],
  });
}

// ================= CONSTRUCTION DU DOCUMENT =================
const children = [];

// ----- PAGE DE TITRE -----
children.push(new Paragraph({ spacing: { before: 1200 }, children: [] }));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 120 },
  children: [new TextRun({ text: "Data Lake médical : de l'ECG à l'EEG", bold: true, color: NAVY, font: FONT, size: 48 })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 600 },
  children: [new TextRun({ text: "Ingestion, transformation, Machine Learning et exposition via API", italics: true, color: GREY, font: FONT, size: 28 })],
}));
children.push(placeholder("[ INSÉRER UNE IMAGE DE COUVERTURE — ex. un tracé ECG/EEG stylisé ou un schéma d'architecture ]"));
children.push(new Paragraph({ spacing: { before: 800 }, children: [] }));
children.push(identityTable());
children.push(new Paragraph({ children: [new PageBreak()] }));

// ----- SOMMAIRE -----
children.push(h1("Sommaire"));
children.push(new TableOfContents("Sommaire", { hyperlink: true, headingStyleRange: "1-2" }));
children.push(new Paragraph({ children: [new TextRun({ text: "(Dans Word : clic droit sur le sommaire → « Mettre à jour les champs » pour générer les numéros de page.)", italics: true, color: GREY, font: FONT, size: 18 })] }));
children.push(new Paragraph({ children: [new PageBreak()] }));

// ===== 0. COMMENT LANCER LE PROJET =====
children.push(h1("0. Comment lancer ce projet"));
children.push(p("Ce projet se lance en local grâce à Docker. Les commandes ci-dessous démarrent l'entrepôt de fichiers (MinIO) et la base de données (PostgreSQL), installent les dépendances Python, puis exécutent le pipeline et l'API."));
children.push(h2("Prérequis"));
children.push(bullet("Docker Desktop (pour les services)."));
children.push(bullet("Python 3.10 ou supérieur (pour le code)."));
children.push(h2("Étapes"));
children.push(bullet("Copier la configuration : cp .env.example .env"));
children.push(bullet("Démarrer les services : docker-compose up -d"));
children.push(bullet("Installer les dépendances : pip install -r requirements.txt"));
children.push(bullet("Créer les buckets : python -m src.storage.minio_client"));
children.push(bullet("Lancer le pipeline / l'API / le dashboard (commandes détaillées dans le README)."));
children.push(placeholder("[ À COMPLÉTER une fois les étapes 1-4 codées : commandes exactes pour lancer un DAG Airflow, démarrer l'API FastAPI et ouvrir le dashboard Streamlit. ]"));
children.push(tip("Recopier ici la version définitive et testée des commandes de ton README, pour que le correcteur puisse builder sans galérer. Le sujet insiste beaucoup là-dessus."));

// ===== 1. INTRODUCTION =====
children.push(h1("1. Pourquoi ce projet"));
children.push(p("J'ai choisi de construire un data lake sur des signaux physiologiques médicaux (électrocardiogrammes et électroencéphalogrammes) plutôt que sur un jeu de données générique. C'est un domaine où les données sont réellement hétérogènes — des signaux temporels multicanaux, volumineux, au format binaire — ce qui correspond exactement à ce qu'un data lake est censé savoir gérer et valoriser."));
children.push(p("Au-delà de la simple validation des acquis du cours, mon objectif était de construire une plateforme qui ne soit pas jetable : une infrastructure d'ingestion générique dans laquelle on peut brancher plusieurs sources de nature différente sans tout réécrire. C'est le fil directeur de tout le projet."));

children.push(h2("1.1 La question de départ"));
children.push(p("Concrètement, la question que je me suis posée est la suivante : peut-on construire une chaîne de traitement de bout en bout — de l'ingestion d'un signal médical brut jusqu'à une prédiction exposée via une API — qui soit à la fois robuste, reproductible et extensible à un nouveau type de signal ? Je m'intéresse autant à la qualité de l'architecture qu'à la performance du modèle."));

children.push(h2("1.2 Les sources de données"));
children.push(p("Conformément à la consigne (une source fichier et une source API), j'utilise :"));
children.push(bullet("un jeu de données PhysioNet (signaux ECG puis EEG), lu à l'aide des librairies spécialisées, comme source fichier ;", "Source fichier —"));
children.push(bullet("une API publique temps réel, interrogée à intervalle régulier par le pipeline, comme source API.", "Source API —"));
children.push(placeholder("[ À COMPLÉTER : préciser les datasets exacts retenus (ex. MIT-BIH Arrhythmia, CHB-MIT Scalp EEG) et l'API exacte (ex. OpenAQ), avec un lien vers chaque source. ]"));

children.push(h2("1.3 Un principe directeur : une infrastructure, plusieurs domaines"));
children.push(p("Le choix d'architecture le plus important du projet est de ne pas traiter l'ECG et l'EEG comme deux projets séparés. Toute la « tuyauterie » (stockage, transformation, base finale, orchestration, API) est écrite une seule fois. Chaque type de signal n'est qu'un connecteur qui se branche dessus. Ajouter l'EEG après l'ECG ne demande donc presque aucun code nouveau — c'est la démonstration concrète que l'architecture est pensée pour grandir."));

// ===== 2. ARCHITECTURE =====
children.push(h1("2. L'architecture du data lake"));
children.push(h2("2.1 Les quatre zones (architecture medallion)"));
children.push(p("Le data lake est organisé en zones successives, chacune correspondant à un état de raffinement des données : raw (le brut, jamais modifié), staging (le nettoyé et transformé en features), curated (les données propres enrichies du résultat du modèle), puis une couche d'exposition (API et dashboard). Garder le brut intact en zone raw est une règle d'or : on peut toujours tout recalculer depuis la source si on découvre une erreur de traitement."));
children.push(placeholder("[ INSÉRER LE SCHÉMA D'ARCHITECTURE — les 4 zones et le flux des données. (Voir ARCHITECTURE.md pour le contenu.) ]"));

children.push(h2("2.2 Les choix techniques et leur justification"));
children.push(bullet("un « S3 maison », gratuit et conforme à la consigne (S3 imposé pour la zone raw), qui stocke aussi bien les fichiers binaires que les payloads JSON.", "MinIO (raw & staging) —"));
children.push(bullet("base relationnelle robuste pour ranger les données finales structurées, une ligne par événement analysé.", "PostgreSQL (curated) —"));
children.push(bullet("l'orchestrateur qui déclenche les tâches automatiquement et gère le scheduling de l'ingestion API.", "Apache Airflow —"));
children.push(bullet("pour exposer les endpoints, avec un support natif de l'asynchrone utile au niveau avancé.", "FastAPI —"));
children.push(bullet("pour le dashboard de visualisation, écrit en Python pur.", "Streamlit —"));
children.push(bullet("pour lancer toute l'infrastructure d'une seule commande, à l'identique sur n'importe quelle machine.", "Docker Compose —"));
children.push(tip("Si tu changes un choix techno en cours de route (ex. TimescaleDB au lieu de Postgres), mets à jour cette liste et explique pourquoi — le prof valorise la justification des choix."));

children.push(h2("2.3 Le pattern « processeur enfichable »"));
children.push(p("Techniquement, l'extensibilité repose sur une classe de base abstraite (SignalProcessor) qui décrit la logique commune du pipeline une seule fois. Chaque domaine (ECG, EEG) fournit sa propre implémentation de deux méthodes seulement : lire le signal brut, et en extraire les features. Le reste — l'enchaînement, le stockage, l'écriture en base — est mutualisé. C'est ce qui rend l'ajout d'une nouvelle source quasi gratuit."));

// ===== 3. PIPELINE =====
children.push(h1("3. Le pipeline d'intégration (Airflow)"));
children.push(p("Le pipeline assure la reproductibilité des transformations et l'alimentation automatisée du data lake, sans lancer les scripts à la main."));
children.push(h2("3.1 Les DAGs"));
children.push(p("Chaque source dispose de son propre DAG (graphe de tâches) qui enchaîne : ingestion vers la zone raw, transformation vers staging, puis chargement en curated."));
children.push(placeholder("[ INSÉRER CAPTURE D'ÉCRAN — un DAG affiché en vert dans l'interface Airflow. ]"));
children.push(h2("3.2 Le scheduling de la source API"));
children.push(p("Pour la source API, j'utilise la fonctionnalité de scheduling d'Airflow afin d'ingérer les données à intervalle régulier, ce qui simule un flux continu réaliste."));
children.push(placeholder("[ À COMPLÉTER : la fréquence d'ingestion choisie et, si tu l'as tenté, un mot sur l'usage de XCom pour passer des informations entre tâches. ]"));

// ===== 4. TRAITEMENT PAR ZONE =====
children.push(h1("4. Le traitement, zone par zone"));
children.push(h2("4.1 Zone raw — l'ingestion brute"));
children.push(p("Les fichiers de signaux et les payloads JSON de l'API sont déposés tels quels dans MinIO, rangés par source. Aucun nettoyage à ce stade : on préserve l'original."));
children.push(h2("4.2 Zone staging — l'extraction des features"));
children.push(p("C'est ici que le signal brut devient exploitable. Pour l'ECG, j'extrais des caractéristiques par battement ; pour l'EEG, j'applique un filtrage et je calcule des caractéristiques fréquentielles. Le résultat est stocké au format Parquet."));
children.push(placeholder("[ INSÉRER un extrait des features obtenues (tableau) et décrire brièvement la recette d'extraction propre à chaque signal. ]"));
children.push(h2("4.3 Zone curated — le modèle de Machine Learning"));
children.push(p("Les features nettoyées alimentent un modèle de détection d'anomalies (battements anormaux pour l'ECG, crises pour l'EEG). Les résultats, features et prédiction, sont écrits en base pour être exposés par l'API."));
children.push(placeholder("[ INSÉRER les métriques du modèle (accuracy, F1, matrice de confusion) et un commentaire honnête : où le modèle se trompe-t-il, et pourquoi ? ]"));
children.push(tip("Comme dans le rapport modèle : compare toujours à une baseline naïve. Un score n'a de sens que face à un point de comparaison."));

// ===== 5. API GATEWAY =====
children.push(h1("5. L'API Gateway"));
children.push(p("L'API offre une interface simple pour récupérer les données ingérées sans avoir à manipuler directement l'entrepôt ou la base."));
children.push(h2("5.1 Les endpoints"));
children.push(endpointsTable());
children.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
children.push(h2("5.2 Exemples de réponses"));
children.push(placeholder("[ INSÉRER CAPTURES — exemples d'appels et de réponses JSON (ex. /health, /stats, /curated). ]"));

// ===== 6. NIVEAU AVANCÉ =====
children.push(h1("6. Niveau avancé : /ingest et /ingest_fast"));
children.push(p("Cette partie répond au niveau avancé du sujet : exposer un endpoint d'ingestion, mesurer ses performances, puis en proposer une version optimisée d'au moins 30 % plus rapide."));
children.push(h2("6.1 L'approche"));
children.push(p("L'endpoint /ingest accepte des données au format JSON et les propage à travers le pipeline. Je chronomètre son temps d'exécution sur deux tailles de lot : un seul élément, puis cent éléments. Ces mesures servent de base de comparaison."));
children.push(h2("6.2 Les optimisations mises en place"));
children.push(placeholder("[ À COMPLÉTER : lister les optimisations réellement utilisées pour /ingest_fast (vectorisation NumPy, traitement asynchrone, parallélisme, mise en cache, Numba…) et expliquer en une phrase pourquoi chacune accélère le traitement. ]"));
children.push(h2("6.3 Résultats comparés"));
children.push(perfTable());
children.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
children.push(placeholder("[ À COMPLÉTER : commenter le gain obtenu. As-tu dépassé les 30 % exigés ? Sur quelle taille de batch le gain est-il le plus net, et pourquoi ? ]"));
children.push(tip("C'est LA section qui rapporte le t-shirt. Sois précis sur la méthode de mesure (moyenne sur N essais, machine utilisée) pour que les chiffres soient crédibles."));

// ===== 7. DASHBOARD =====
children.push(h1("7. Le dashboard médical"));
children.push(p("Le dashboard consomme uniquement l'API (jamais la base directement) et permet de visualiser les signaux ingérés ainsi que les détections du modèle."));
children.push(placeholder("[ INSÉRER CAPTURES du dashboard — vue des signaux, alertes de détection, métriques du data lake. ]"));

// ===== 8. LIMITES =====
children.push(h1("8. Limites et honnêteté"));
children.push(p("Plutôt que de présenter le projet comme parfait, je préfère assumer clairement ses limites — c'est plus utile et plus honnête."));
children.push(bullet("les signaux médicaux réels contiennent des artefacts (mouvements, perte de contact des capteurs) que mon prétraitement ne gère que partiellement.", "Qualité des données —"));
children.push(bullet("les événements rares (crises, arythmies) sont minoritaires, ce qui complique l'apprentissage et impose des précautions (pondération des classes).", "Déséquilibre des classes —"));
children.push(bullet("les mesures de /ingest_fast dépendent de la machine et de la charge ; elles illustrent un gain, elles ne constituent pas un benchmark industriel.", "Performances —"));
children.push(placeholder("[ À PERSONNALISER : ajoute les limites concrètes que TU as rencontrées en construisant le projet. C'est cette honnêteté qui distingue un bon rapport. ]"));

// ===== 9. CE QUE JE RETIENS =====
children.push(h1("9. Ce que je retiens de ce projet"));
children.push(tip("Cette section doit être écrite par toi, avec tes vrais mots. Voici des pistes de réflexion pour t'aider à démarrer — remplace-les par ton vécu."));
children.push(bullet("Qu'est-ce que le pattern « une infra, plusieurs domaines » m'a appris sur la conception de systèmes de données ?"));
children.push(bullet("Qu'est-ce qui a été plus dur que prévu (Docker ? l'orchestration Airflow ? le déséquilibre des classes ?) et comment je l'ai résolu ?"));
children.push(bullet("Qu'est-ce que l'optimisation /ingest_fast m'a appris sur la différence entre « ça marche » et « c'est performant » ?"));
children.push(bullet("Si je devais continuer le projet, quelle serait la prochaine amélioration ?"));
children.push(placeholder("[ À RÉDIGER : ta conclusion personnelle, honnête, sur ce que ce projet t'a apporté techniquement. ]"));

// ===== ANNEXES =====
children.push(h1("Annexes"));
children.push(bullet("Dépôt GitHub : [ INSÉRER LE LIEN ]"));
children.push(bullet("Sources de données : [ INSÉRER LES LIENS des datasets et de l'API ]"));
children.push(bullet("Documentation interne : ARCHITECTURE.md, SPECS.md, GUIDE.md (fournis dans le dépôt)."));

// ---------- Assemblage ----------
const doc = new Document({
  creator: "Projet Data Lake",
  title: "Rapport — Data Lake médical",
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
  },
  numbering: {
    config: [{
      reference: "puces",
      levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT }],
    }],
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 } } }, // US Letter
    headers: { default: header },
    footers: { default: footer },
    children,
  }],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync("Rapport_DataLake_Medical_TEMPLATE.docx", buffer);
  console.log("✅ Rapport généré : Rapport_DataLake_Medical_TEMPLATE.docx");
});
