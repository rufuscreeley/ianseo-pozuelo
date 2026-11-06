"""Scraper de Ianseo: competiciones completadas de España (2026) -> CSV con los
resultados (individuales y por equipos) del club Arqueros de Pozuelo.

Páginas que descarga de cada competición (la versión .php, no el PDF):
  IF*  clasificación final individual (Final Round - Ranking)
  TF*  clasificación final por equipos (Final Round - Ranking)
  IC   clasificación por clase y división (competiciones regionales)

Uso:
  python scraper.py                 # ejecución normal (solo procesa lo nuevo o cambiado)
  python scraper.py --debug 28562   # procesa solo esa competición, guarda su HTML en debug/
                                    # y las filas encontradas en debug/filas_<toId>.csv
  python scraper.py --todas         # incluye también clasificación (IQ/TQ) y cuadros (IB/TB)
"""
import argparse, csv, hashlib, json, re, sys, time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ianseo.net/"
LIST_URL = BASE + "TourList.php?Year=2026&countryid=ESP&comptime=2&timeType=local"
# El club en Ianseo: código 2138 ("2138 - Cde Arqueros De Pozuelo"); en competiciones regionales
# aparece como "POZUE - ...". Además se busca por nombre. \b y el guion evitan falsos positivos:
# el apellido "POZUELO" o puntuaciones que valgan 2138.
CLUB_RE = re.compile(r"\b2138\s*-\s*[A-Za-z]|\bPOZUE\b|ARQUEROS\s+(?:DE\s+)?POZUELO", re.IGNORECASE)
HEADERS = {"User-Agent": "ArquerosPozuelo-resultados/1.0 (contacto: TU_EMAIL)"}
PAUSE = 1.0  # segundos entre peticiones
MIN_MIEMBROS = 2  # un equipo es del club si aparecen al menos 2 de sus atletas individuales

DATA = Path("data")
COMP_CSV, STATE = DATA / "competiciones.csv", DATA / "state.json"
NAC_CSV, REG_CSV = DATA / "resultados_nacionales.csv", DATA / "resultados_regionales.csv"
RES_COLS = ["toId", "competicion", "codigo_pagina", "tipo", "evento", "division", "categoria",
            "posicion_final", "atleta", "club_codigo", "club", "equipo_codigo", "equipo", "miembros",
            "ronda1_puntos", "ronda1_posicion", "ronda2_puntos", "ronda2_posicion",
            "puntos_totales", "dieces", "nueves", "resto", "celdas", "contexto", "url", "extraido"]
# Nacionales (RFETA): páginas IF*/TF*, solo posición final -> sin columnas de puntuación.
COLS_NAC = ["toId", "competicion", "tipo", "division", "categoria", "posicion_final",
            "atleta", "club", "equipo", "miembros", "url", "extraido"]
# Regionales (página IC): incluyen puntos por ronda, total, dieces y nueves.
COLS_REG = ["toId", "competicion", "tipo", "division", "categoria", "posicion_final", "atleta", "club",
            "ronda1_puntos", "ronda1_posicion", "ronda2_puntos", "ronda2_posicion",
            "puntos_totales", "dieces", "nueves", "resto", "url", "extraido"]
RESULT_PAGE = re.compile(r"/((?:I|T)[A-Z0-9]{1,4})\.php$")  # IC, IFRM, TFRM2, IQRM...
PAGINAS_BASE = ("IF", "TF", "IC")
CELDA_CLUB = re.compile(r"^(\S+) - (\S.*)$")                # "2138 - Cde Arqueros De Pozuelo"
DETALLE = re.compile(r"\d\s*:\s*\d")                        # "18m-1: 258 , 18m-2: 232"
PUNTOS_RONDA = re.compile(r"(\d+)\s*/\s*(\d+)")              # "284/ 1" = puntos / posición en la ronda
DIVISIONES = r"Arco Instintivo|Recurvo|Compuesto|Desnudo|Tradicional|Longbow|Instintivo|Barebow"

S = requests.Session()
S.headers.update(HEADERS)


def get(url):
    for intento in range(3):
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 200:
                time.sleep(PAUSE)
                return r.text
            print(f"  HTTP {r.status_code}: {url}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  error: {e}", file=sys.stderr)
        time.sleep(5 * (intento + 1))
    return None


def listar_competiciones(debug=False):
    try:
        r = S.get(LIST_URL, timeout=30)
    except requests.RequestException as e:
        sys.exit(f"No se pudo descargar el listado: {e}")
    html = r.text
    soup = BeautifulSoup(html, "lxml")
    titulo = soup.title.get_text(strip=True) if soup.title else "(sin título)"
    print(f"Listado: HTTP {r.status_code}, {len(html)} caracteres, título: {titulo!r}, "
          f"apariciones de 'toId': {html.count('toId')}")
    Path("debug").mkdir(exist_ok=True)
    Path("debug/listado.html").write_text(html, encoding="utf-8")
    comps = {}
    for tr in soup.find_all("tr"):
        if tr.find("tr"):
            continue
        m = re.search(r"toId=(\d+)", str(tr))  # busca en href, onclick, data-*...
        if m:
            comps[m.group(1)] = {"toId": m.group(1), "fila": " ".join(tr.stripped_strings)}
    if not comps:
        print("No se encontraron competiciones. Primeros 500 caracteres:\n" + html[:500], file=sys.stderr)
        if not debug:
            sys.exit("El listado no contiene competiciones: ¿bloqueo o HTML distinto? Mira debug/listado.html")
    time.sleep(PAUSE)
    return comps


def paginas_resultados(tid, soup, url, todas):
    vistas, out = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        m = RESULT_PAGE.search(href)
        if not m or f"/{tid}/" not in href or href in vistas:
            continue
        codigo = m.group(1)
        if not todas and not codigo.startswith(PAGINAS_BASE):
            continue
        vistas.add(href)
        out.append((codigo, a.get_text(" ", strip=True), href))
    return out


def norm(t):
    t = re.sub(r"&nbsp;?", " ", t)  # Ianseo deja "&nbsp" literal en algunas celdas
    t = re.sub(r"\s+", " ", t).strip()
    return t.replace(" ; ", "; ")  # separador de los componentes de un equipo (<br>)


def filas_club(codigo, html, nombres=()):
    """Filas del club en una página de resultados, con la sección en la que aparecen.
    - Individuales (I*): filas que mencionan al club (código 2138, POZUE o nombre).
    - Equipos (T*): el nombre del equipo no incluye el código del club (p. ej. "RH102 - Arcopozuelo A"),
      pero solo compiten por equipos atletas que compiten en individual: se reconocen por los
      nombres de los atletas del club ya encontrados en la competición."""
    es_equipo = codigo.startswith("T")
    if not es_equipo and not CLUB_RE.search(html):
        return []
    soup = BeautifulSoup(html, "lxml")
    for br in soup.find_all("br"):
        br.replace_with(" ; ")  # separa los componentes de un equipo
    res, seccion, previa = [], "", []
    for tr in soup.find_all("tr"):
        if tr.find("tr"):
            continue
        celdas = [norm(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        llenas = [c for c in celdas if c]
        if len(llenas) == 1:
            # fila de una sola celda: título de sección, salvo que sea el detalle de la fila anterior
            # (repite el club o los componentes, o muestra "18m-1: 258, 18m-2: 232")
            if not any(llenas[0] in c for c in previa) and not DETALLE.search(llenas[0]):
                seccion = llenas[0]
            continue
        if len(llenas) < 3:
            continue
        texto = " ".join(celdas)
        if es_equipo:
            ok = bool(CLUB_RE.search(texto)) or sum(1 for n in nombres if n in texto) >= MIN_MIEMBROS
        else:
            ok = bool(CLUB_RE.search(texto))
        previa = celdas
        if ok:
            res.append((celdas, seccion))
    return res


def separar(celdas, es_equipo):
    """Reparte las celdas de una fila en campos con nombre (y devuelve las celdas sobrantes)."""
    d = {"posicion_final": celdas[0], "atleta": "", "club_codigo": "", "club": "",
         "equipo_codigo": "", "equipo": "", "miembros": ""}
    minimo = 1 if es_equipo else 2  # en individuales el club va después del nombre
    idx = next((i for i, c in enumerate(celdas) if i >= minimo and CELDA_CLUB.match(c)), None)
    if idx is None:
        rest = celdas[2:]
        d["miembros" if es_equipo else "atleta"] = celdas[1] if len(celdas) > 1 else ""
    else:
        codigo, nombre = CELDA_CLUB.match(celdas[idx]).groups()
        if es_equipo:
            d["equipo_codigo"], d["equipo"] = codigo, nombre
            d["miembros"] = celdas[idx + 1] if len(celdas) > idx + 1 else ""
            rest = celdas[idx + 2:]
        else:
            d["atleta"] = celdas[1]
            d["club_codigo"], d["club"] = codigo, nombre
            rest = celdas[idx + 1:]
    return d, [c for c in rest if c]


def puntuaciones(resto):
    """Reparte las celdas de puntuación. Si no encajan con el formato conocido
    (2 rondas "puntos/posición" + total, dieces y nueves; en equipos sin rondas), van a 'resto'."""
    rondas, otros = [], []
    for c in resto:
        m = PUNTOS_RONDA.fullmatch(c)
        (rondas if m else otros).append(m.groups() if m else c)
    out = {k: "" for k in ("ronda1_puntos", "ronda1_posicion", "ronda2_puntos", "ronda2_posicion",
                           "puntos_totales", "dieces", "nueves", "resto")}
    if len(otros) == 3 and len(rondas) in (0, 2):
        if rondas:
            out["ronda1_puntos"], out["ronda1_posicion"] = rondas[0]
            out["ronda2_puntos"], out["ronda2_posicion"] = rondas[1]
        out["puntos_totales"], out["dieces"], out["nueves"] = otros
    elif resto:
        out["resto"] = " | ".join(resto)
    return out


def dividir(seccion):
    """'Recurvo - Plus 50 Hombre' -> ('Recurvo', 'Plus 50 Hombre');
    'Equipo Recurvo Hombre 1º división' -> ('Recurvo', 'Hombre 1º división')."""
    if " - " in seccion:
        d, _, c = seccion.partition(" - ")
        return d, c
    m = re.match(rf"^(?:Equipo\s+)?({DIVISIONES})\s+(.*)$", seccion, re.IGNORECASE)
    return (m.group(1), m.group(2)) if m else ("", seccion)


def procesar(tid, nombre, fp_anterior, todas, debug=False):
    url = f"{BASE}Details.php?toId={tid}"
    html = get(url)
    if not html:
        return None, None
    soup = BeautifulSoup(html, "lxml")
    # huella: todos los enlaces a TourData (los PDF llevan ?time=... y cambian al actualizarse)
    huella = hashlib.md5("|".join(sorted(a["href"] for a in soup.find_all("a", href=True) if "TourData" in a["href"])).encode()).hexdigest()
    if huella == fp_anterior and not debug:
        return huella, None
    img = soup.select_one('img[src*="Header/topleft"]')
    if img and img.get("alt"):
        nombre = norm(img["alt"])
    filas = []
    if debug:
        d = Path("debug") / tid
        d.mkdir(parents=True, exist_ok=True)
        (d / "Details.html").write_text(html, encoding="utf-8")
    paginas = paginas_resultados(tid, soup, url, todas)
    paginas.sort(key=lambda p: p[0].startswith("T"))  # primero las individuales
    nombres = set()
    for codigo, evento, href in paginas:
        es_equipo = codigo.startswith("T")
        if es_equipo and not nombres:
            continue  # sin atletas individuales del club no puede haber equipos del club
        h = get(href)
        if not h:
            continue
        if debug:
            (Path("debug") / tid / f"{codigo}.html").write_text(h, encoding="utf-8")
        for celdas, seccion in filas_club(codigo, h, nombres):
            campos, resto = separar(celdas, es_equipo)
            if not es_equipo and campos["atleta"]:
                nombres.add(campos["atleta"])
            division, categoria = dividir(seccion or evento)
            fila = {
                "toId": tid, "competicion": nombre, "codigo_pagina": codigo,
                "tipo": "Equipos" if es_equipo else "Individual", "evento": evento,
                "division": division, "categoria": categoria,
                "celdas": " | ".join(celdas), "contexto": "",
                "url": href, "extraido": date.today().isoformat(),
            }
            fila.update(campos)
            fila.update(puntuaciones(resto))
            filas.append(fila)
    return huella, filas


def leer_csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def escribir_csv(path, filas, cols):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", metavar="TOID")
    ap.add_argument("--todas", action="store_true")
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)

    comps = listar_competiciones(bool(args.debug))
    if args.debug:
        comps = {args.debug: comps.get(args.debug, {"toId": args.debug, "fila": ""})}
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    nac, reg = leer_csv(NAC_CSV), leer_csv(REG_CSV)
    nuevas = [t for t in comps if t not in state]
    print(f"{len(comps)} competiciones en el listado, {len(nuevas)} nuevas")

    for i, (tid, c) in enumerate(comps.items(), 1):
        huella, filas = procesar(tid, c["fila"], state.get(tid), args.todas, bool(args.debug))
        if huella is None:
            continue  # fallo de red: se reintentará el mes siguiente
        if filas is not None:
            es_nac = lambda f: f["codigo_pagina"].startswith(("IF", "TF"))
            nac = [r for r in nac if r["toId"] != tid] + [f for f in filas if es_nac(f)]
            reg = [r for r in reg if r["toId"] != tid] + [f for f in filas if not es_nac(f)]
            print(f"[{i}/{len(comps)}] {tid}: {len(filas)} filas del club")
        if args.debug and filas:
            for f in filas:
                quien = f["miembros"] if f["tipo"] == "Equipos" else f["atleta"]
                nombre = f["equipo"] if f["tipo"] == "Equipos" else f["club"]
                pts = ""
                if f["puntos_totales"] or f["resto"]:
                    pts = (f" | R1 {f['ronda1_puntos']}/{f['ronda1_posicion']} R2 {f['ronda2_puntos']}/{f['ronda2_posicion']} "
                           f"total {f['puntos_totales']} 10:{f['dieces']} 9:{f['nueves']} {f['resto']}").rstrip()
                print(f"  [{f['codigo_pagina']}] {f['division']} | {f['categoria']} | pos {f['posicion_final']} | {quien} | {nombre}{pts}")
            escribir_csv(Path("debug") / f"filas_{tid}.csv", filas, RES_COLS)
        if not args.debug:
            state[tid] = huella

    if args.debug:
        return
    escribir_csv(COMP_CSV, [{"toId": t, "fila": c["fila"]} for t, c in comps.items()], ["toId", "fila"])
    escribir_csv(NAC_CSV, nac, COLS_NAC)
    escribir_csv(REG_CSV, reg, COLS_REG)
    STATE.write_text(json.dumps(state, indent=1))


if __name__ == "__main__":
    main()