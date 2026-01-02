# Subito.it Location Data
# Mapping for URL construction and UI dropdowns

REGIONS = [
    ("abruzzo", "Abruzzo"),
    ("basilicata", "Basilicata"),
    ("calabria", "Calabria"),
    ("campania", "Campania"),
    ("emilia-romagna", "Emilia Romagna"),
    ("friuli-venezia-giulia", "Friuli Venezia Giulia"),
    ("lazio", "Lazio"),
    ("liguria", "Liguria"),
    ("lombardia", "Lombardia"),
    ("marche", "Marche"),
    ("molise", "Molise"),
    ("piemonte", "Piemonte"),
    ("puglia", "Puglia"),
    ("sardegna", "Sardegna"),
    ("sicilia", "Sicilia"),
    ("toscana", "Toscana"),
    ("trentino-alto-adige", "Trentino Alto Adige"),
    ("umbria", "Umbria"),
    ("valle-daosta", "Valle d'Aosta"),
    ("veneto", "Veneto"),
]

# Region Slug -> List of (Province Slug, Province Name)
PROVINCES = {
    "abruzzo": [
        ("chieti", "Chieti"), ("la-quila", "L'Aquila"), ("pescara", "Pescara"), ("teramo", "Teramo")
    ],
    "basilicata": [
        ("matera", "Matera"), ("potenza", "Potenza")
    ],
    "calabria": [
        ("catanzaro", "Catanzaro"), ("cosenza", "Cosenza"), ("crotone", "Crotone"), 
        ("reggio-calabria", "Reggio Calabria"), ("vibo-valentia", "Vibo Valentia")
    ],
    "campania": [
        ("avellino", "Avellino"), ("benevento", "Benevento"), ("caserta", "Caserta"), 
        ("napoli", "Napoli"), ("salerno", "Salerno")
    ],
    "emilia-romagna": [
        ("bologna", "Bologna"), ("ferrara", "Ferrara"), ("forli-cesena", "Forlì-Cesena"), 
        ("modena", "Modena"), ("parma", "Parma"), ("piacenza", "Piacenza"), 
        ("ravenna", "Ravenna"), ("reggio-emilia", "Reggio Emilia"), ("rimini", "Rimini")
    ],
    "friuli-venezia-giulia": [
        ("gorizia", "Gorizia"), ("pordenone", "Pordenone"), ("trieste", "Trieste"), ("udine", "Udine")
    ],
    "lazio": [
        ("frosinone", "Frosinone"), ("latina", "Latina"), ("rieti", "Rieti"), 
        ("roma", "Roma"), ("viterbo", "Viterbo")
    ],
    "liguria": [
        ("genova", "Genova"), ("imperia", "Imperia"), 
        ("la-spezia", "La Spezia"), ("savona", "Savona")
    ],
    "lombardia": [
        ("bergamo", "Bergamo"), ("brescia", "Brescia"), ("como", "Como"), 
        ("cremona", "Cremona"), ("lecco", "Lecco"), ("lodi", "Lodi"), 
        ("mantova", "Mantova"), ("milano", "Milano"), ("monza-brianza", "Monza e Brianza"), 
        ("pavia", "Pavia"), ("sondrio", "Sondrio"), ("varese", "Varese")
    ],
    "marche": [
        ("ancona", "Ancona"), ("ascoli-piceno", "Ascoli Piceno"), ("fermo", "Fermo"), 
        ("macerata", "Macerata"), ("pesaro-urbino", "Pesaro e Urbino")
    ],
    "molise": [
        ("campobasso", "Campobasso"), ("isernia", "Isernia")
    ],
    "piemonte": [
        ("alessandria", "Alessandria"), ("asti", "Asti"), ("biella", "Biella"), 
        ("cuneo", "Cuneo"), ("novara", "Novara"), ("torino", "Torino"), 
        ("verbano-cusio-ossola", "Verbano-Cusio-Ossola"), ("vercelli", "Vercelli")
    ],
    "puglia": [
        ("bari", "Bari"), ("barletta-andria-trani", "Barletta-Andria-Trani"), 
        ("brindisi", "Brindisi"), ("foggia", "Foggia"), ("lecce", "Lecce"), ("taranto", "Taranto")
    ],
    "sardegna": [
        ("cagliari", "Cagliari"), ("nuoro", "Nuoro"), ("oristano", "Oristano"), 
        ("sassari", "Sassari"), ("sud-sardegna", "Sud Sardegna")
    ],
    "sicilia": [
        ("agrigento", "Agrigento"), ("caltanissetta", "Caltanissetta"), ("catania", "Catania"), 
        ("enna", "Enna"), ("messina", "Messina"), ("palermo", "Palermo"), 
        ("ragusa", "Ragusa"), ("siracusa", "Siracusa"), ("trapani", "Trapani")
    ],
    "toscana": [
        ("arezzo", "Arezzo"), ("firenze", "Firenze"), ("grosseto", "Grosseto"), 
        ("livorno", "Livorno"), ("lucca", "Lucca"), ("massa-carrara", "Massa-Carrara"), 
        ("pisa", "Pisa"), ("pistoia", "Pistoia"), ("prato", "Prato"), ("siena", "Siena")
    ],
    "trentino-alto-adige": [
        ("bolzano", "Bolzano"), ("trento", "Trento")
    ],
    "umbria": [
        ("perugia", "Perugia"), ("terni", "Terni")
    ],
    "valle-daosta": [
        ("aosta", "Aosta")
    ],
    "veneto": [
        ("belluno", "Belluno"), ("padova", "Padova"), ("rovigo", "Rovigo"), 
        ("treviso", "Treviso"), ("venezia", "Venezia"), ("verona", "Verona"), ("vicenza", "Vicenza")
    ]
}
