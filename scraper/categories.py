# Codici dell'API Hades di Subito (parametro "c"): accetta sia le macrocategorie
# sia le categorie. Ricavati da category.key e category.macrocategory_id
# degli annunci restituiti dall'API.
MACROCATEGORIES = [
    ("9", "Elettronica", [
        ("10", "Informatica"),
        ("11", "Audio/Video"),
        ("12", "Telefonia"),
        ("40", "Fotografia"),
        ("44", "Console e Videogiochi"),
    ]),
    ("13", "Casa e persona", [
        ("14", "Arredamento e Casalinghi"),
        ("37", "Elettrodomestici"),
        ("15", "Giardino e Fai da te"),
        ("16", "Abbigliamento e Accessori"),
        ("17", "Tutto per i bambini"),
    ]),
    ("18", "Sport e hobby", [
        ("20", "Sports"),
        ("41", "Biciclette"),
        ("39", "Strumenti Musicali"),
        ("19", "Musica e Film"),
        ("38", "Libri e Riviste"),
        ("21", "Collezionismo"),
        ("23", "Animali"),
        ("100", "Accessori per animali"),
    ]),
    ("1", "Motori", [
        ("2", "Auto"),
        ("3", "Moto e Scooter"),
        ("4", "Veicoli commerciali"),
        ("5", "Accessori Auto"),
        ("36", "Accessori Moto"),
        ("34", "Caravan e Camper"),
        ("22", "Nautica"),
    ]),
    ("6", "Immobili", [
        ("7", "Appartamenti"),
        ("29", "Ville singole e a schiera"),
        ("30", "Terreni e rustici"),
        ("8", "Uffici e Locali commerciali"),
        ("31", "Garage e box"),
        ("32", "Loft, mansarde e altro"),
        ("33", "Case vacanza"),
        ("43", "Camere/Posti letto"),
    ]),
    ("24", "Lavoro e servizi", [
        ("25", "Attrezzature di lavoro"),
        ("50", "Servizi"),
        ("26", "Offerte di lavoro"),
        ("42", "Candidati in cerca di lavoro"),
    ]),
    # Macrocategoria con un'unica categoria ("Altri", codice 28)
    ("27", "Altri", []),
]

CATEGORY_NAMES = {}
for macro_key, macro_name, cats in MACROCATEGORIES:
    CATEGORY_NAMES[macro_key] = macro_name
    CATEGORY_NAMES.update(cats)
