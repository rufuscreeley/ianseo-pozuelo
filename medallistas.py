"""Los tres atletas con más medallas individuales (puestos 1 a 3), en total y por año, con el nombre de la foto que usa la web."""
import csv, collections, re, unicodedata
import scraper

def slug(nombre):
    t = "".join(c for c in unicodedata.normalize("NFD", nombre) if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")

filas = []
for fichero in ("data/resultados_nacionales.csv", "data/resultados_regionales.csv"):
    with open(fichero, encoding="utf-8", newline="") as f:
        filas += [r for r in csv.DictReader(f) if r["tipo"] == "Individual" and r["posicion_final"] in ("1", "2", "3")]

def top3(rows):
    medallas = collections.defaultdict(lambda: [0, 0, 0])
    cuenta = collections.Counter(r["atleta"] for r in rows if r["atleta"])
    mapa, _ = scraper.agrupar_nombres(cuenta)
    for r in rows:
        medallas[mapa.get(scraper.norm(r["atleta"]), r["atleta"])][int(r["posicion_final"]) - 1] += 1
    return sorted(medallas.items(), key=lambda x: (-x[1][0], -x[1][1], -x[1][2], x[0]))[:3]

def mostrar(titulo, rows):
    print(titulo)
    for k, (nombre, m) in enumerate(top3(rows), 1):
        print(f"  {k}. {nombre}  oro {m[0]} · plata {m[1]} · bronce {m[2]}   -> fotos/{slug(nombre)}.jpg")

mostrar("EN TOTAL (desde 2021)", filas)
for anio in sorted({r["fecha_inicio"][:4] for r in filas}, reverse=True):
    mostrar(f"AÑO {anio}", [r for r in filas if r["fecha_inicio"][:4] == anio])
