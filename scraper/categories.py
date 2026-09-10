# Codici categoria dell'API Hades di Subito (parametro "c").
# Ricavati dal campo category.key degli annunci restituiti dall'API.
CATEGORY_GROUPS = [
    ("Elettronica", [
        ("10", "Informatica"),
        ("11", "Audio/Video"),
        ("12", "Telefonia"),
        ("40", "Fotografia"),
        ("44", "Console e Videogiochi"),
    ]),
    ("Casa e persona", [
        ("14", "Arredamento e Casalinghi"),
        ("37", "Elettrodomestici"),
        ("15", "Giardino e Fai da te"),
        ("16", "Abbigliamento e Accessori"),
        ("17", "Tutto per i bambini"),
    ]),
    ("Sport e hobby", [
        ("20", "Sports"),
        ("41", "Biciclette"),
        ("39", "Strumenti Musicali"),
        ("19", "Musica e Film"),
        ("38", "Libri e Riviste"),
        ("21", "Collezionismo"),
    ]),
    ("Motori", [
        ("2", "Auto"),
        ("3", "Moto e Scooter"),
        ("4", "Veicoli commerciali"),
        ("5", "Accessori Auto"),
        ("36", "Accessori Moto"),
        ("34", "Caravan e Camper"),
        ("22", "Nautica"),
    ]),
    ("Animali", [
        ("23", "Animali"),
        ("100", "Accessori per animali"),
    ]),
    ("Immobili", [
        ("7", "Appartamenti"),
        ("29", "Ville singole e a schiera"),
        ("8", "Uffici e Locali commerciali"),
        ("31", "Garage e box"),
        ("32", "Loft, mansarde e altro"),
        ("33", "Case vacanza"),
        ("43", "Camere/Posti letto"),
    ]),
    ("Altro", [
        ("25", "Attrezzature di lavoro"),
        ("50", "Servizi"),
    ]),
]

CATEGORY_NAMES = {key: name for _, cats in CATEGORY_GROUPS for key, name in cats}
