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
import argparse, csv, hashlib, json, os, re, sys, time, unicodedata
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ianseo.net/"
# Competiciones de España completadas (comptime=2) de cada año, desde PRIMER_ANIO hasta el año en curso
LIST_URL = BASE + "TourList.php?Year={anio}&countryid=ESP&comptime=2&timeType=local"
PRIMER_ANIO = 2021
MAX_SEGUNDOS = float(os.environ.get("MAX_SEGUNDOS", 5.4 * 3600))  # tope por ejecución; lo pendiente sigue en la siguiente
DIAS_REVISION = 60  # una competición terminada hace más días, ya descargada y sin cambios en el listado, no se vuelve a abrir
# El club en Ianseo: código 2138 ("2138 - Cde Arqueros De Pozuelo"); en competiciones regionales
# aparece como "POZUE - ...". Además se busca por nombre. \b y el guion evitan falsos positivos:
# el apellido "POZUELO" o puntuaciones que valgan 2138.
CLUB_RE = re.compile(r"\b2138\s*-\s*[A-Za-z]|\bPOZUE\b|ARQUEROS\s+(?:DE\s+)?POZUELO", re.IGNORECASE)
HEADERS = {"User-Agent": "ArquerosPozuelo-resultados/1.0 (contacto: TU_EMAIL)"}
PAUSE = 1.0  # segundos entre peticiones
CLUB_NOMBRE = "Cde Arqueros De Pozuelo"
MIN_MIEMBROS = 2  # un equipo de club es del club si aparecen al menos 2 de sus atletas individuales
MIN_AUTONOMICO = 1  # en equipos por comunidades autónomas (código de 3 letras: "MAD - Madrid") basta 1 atleta del club

DATA = Path("data")
COMP_CSV, STATE = DATA / "competiciones.csv", DATA / "state.json"
NAC_CSV, REG_CSV = DATA / "resultados_nacionales.csv", DATA / "resultados_regionales.csv"
VERSION_DATOS = "3"  # súbela para que la próxima ejecución vuelva a descargar todas las competiciones
RES_COLS = ["toId", "competicion", "fecha_inicio", "fecha_fin", "lugar", "codigo_pagina", "tipo", "evento",
            "division", "categoria", "genero", "puntos_clasificacion",
            "posicion_final", "atleta", "club_codigo", "club", "equipo_codigo", "equipo", "miembros",
            "ronda1_puntos", "ronda1_posicion", "ronda2_puntos", "ronda2_posicion",
            "puntos_totales", "dieces", "nueves", "resto", "celdas", "contexto", "url", "extraido"]
# Nacionales (RFETA): posición final (páginas IF*/TF*) y puntos de la ronda de clasificación previa (IQ*/TQ*).
COLS_NAC = ["toId", "competicion", "fecha_inicio", "fecha_fin", "lugar", "tipo", "division", "categoria", "genero",
            "posicion_final", "atleta", "club", "equipo", "miembros", "puntos_clasificacion", "url", "extraido"]
# Regionales (página IC): posición final y puntuación final.
COLS_REG = ["toId", "competicion", "fecha_inicio", "fecha_fin", "lugar", "tipo", "division", "categoria", "genero",
            "posicion_final", "atleta", "club", "puntos_totales", "url", "extraido"]
COLS_COMP = ["toId", "codigo", "competicion", "organizador", "lugar", "lugar_original", "fecha", "fecha_inicio", "fecha_fin",
             "actualizado", "url", "filas_club", "ultima_revision"]
ANIO = 2026  # el listado muestra las fechas sin año
MESES = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
RE_FECHA = r"(\d{1,2}\s+[A-Za-z]{3}\s*-\s*\d{1,2}\s+[A-Za-z]{3}|\d{1,2}\s*-\s*\d{1,2}\s+[A-Za-z]{3}|\d{1,2}\s+[A-Za-z]{3})"
RE_ACT = r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{2}:\d{2})"
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


# ---- Lugar: solo localidad, provincia o comunidad (sin calle ni número) ----
COMUNIDADES = {
    "andalucia": "Andalucía", "aragon": "Aragón", "principado de asturias": "Asturias", "asturias": "Asturias",
    "baleares": "Baleares", "islas baleares": "Baleares", "illes balears": "Baleares", "balears": "Baleares",
    "canarias": "Canarias", "cantabria": "Cantabria", "castilla y leon": "Castilla y León",
    "castilla la mancha": "Castilla-La Mancha", "cataluna": "Cataluña", "catalunya": "Cataluña",
    "comunidad valenciana": "Comunidad Valenciana", "comunitat valenciana": "Comunidad Valenciana",
    "extremadura": "Extremadura", "galicia": "Galicia", "comunidad de madrid": "Madrid", "madrid": "Madrid",
    "region de murcia": "Murcia", "murcia": "Murcia", "navarra": "Navarra", "pais vasco": "País Vasco",
    "euskadi": "País Vasco", "la rioja": "La Rioja",
}
PROVINCIAS = {
    "alava": "Álava", "araba": "Álava", "albacete": "Albacete", "alicante": "Alicante", "alacant": "Alicante",
    "almeria": "Almería", "avila": "Ávila", "badajoz": "Badajoz", "barcelona": "Barcelona", "burgos": "Burgos",
    "caceres": "Cáceres", "cadiz": "Cádiz", "castellon": "Castellón", "castello": "Castellón",
    "ciudad real": "Ciudad Real", "cordoba": "Córdoba", "a coruna": "A Coruña", "la coruna": "A Coruña",
    "cuenca": "Cuenca", "girona": "Girona", "gerona": "Girona", "granada": "Granada", "guadalajara": "Guadalajara",
    "gipuzkoa": "Gipuzkoa", "guipuzcoa": "Gipuzkoa", "huelva": "Huelva", "huesca": "Huesca", "jaen": "Jaén",
    "leon": "León", "lleida": "Lleida", "lerida": "Lleida", "lugo": "Lugo", "malaga": "Málaga",
    "ourense": "Ourense", "orense": "Ourense", "palencia": "Palencia", "las palmas": "Las Palmas",
    "pontevedra": "Pontevedra", "rioja": "La Rioja", "salamanca": "Salamanca",
    "santa cruz de tenerife": "Santa Cruz de Tenerife", "segovia": "Segovia", "sevilla": "Sevilla", "soria": "Soria",
    "tarragona": "Tarragona", "teruel": "Teruel", "toledo": "Toledo", "valencia": "Valencia",
    "valladolid": "Valladolid", "bizkaia": "Bizkaia", "vizcaya": "Bizkaia", "zamora": "Zamora",
    "zaragoza": "Zaragoza", "ceuta": "Ceuta", "melilla": "Melilla",
}
_VIAS = ["c/", "c.", "cº", "pº", "calle", "carrer", "cl", "avda", "avenida", "av", "camino", "ctra", "carretera",
         "plaza", "pza", "paseo", "rua", "ronda", "travesia", "urbanizacion", "poligono", "barrio", "finca",
         "alameda", "polideportivo", "poliesportiu", "pabellon", "pavello", "campo", "complejo", "instalaciones",
         "instalacions", "recinto", "club", "c.d", "cd", "cde", "cdm", "cttam", "imd", "estadio", "estadi", "centro",
         "campus", "universidad", "universitat", "ciudad deportiva", "cudad", "escola", "escuela", "colegio",
         "instituto", "gimnasio", "parque", "instalaciones", "arqueros", "tiro", "castell", "castillo", "fronton",
         "hipodromo", "velodromo", "palacio", "sala"]
_RE_VIA = re.compile(r"^(?:" + "|".join(re.escape(v) for v in _VIAS) + r")(?![a-z])")
_RE_NUM = re.compile(r"(?:\d[\w.º]*|s/nº?|nº)", re.IGNORECASE)
_ALIAS = sorted({**PROVINCIAS, **COMUNIDADES}, key=len, reverse=True)
_RE_ALIAS = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(a) for a in _ALIAS) + r")(?![a-z0-9])")
_RE_SEP = re.compile(r"\s*[-–]\s+|\s+/\s+|[,;:()\n]|(?<=[A-Za-zÁ-ú]{5})\.\s+(?=[A-ZÁ-Ú])")
_PARTICULAS = {"de", "del", "la", "las", "los", "el", "y", "i", "en", "d'", "l'", "da", "do", "dos", "das", "a", "e"}

def _titulo(t):
    if t != t.upper() and t != t.lower():
        return t  # ya viene con mayúsculas y minúsculas
    pal = t.lower().split()
    return " ".join(p if (i and p in _PARTICULAS) else p[:1].upper() + p[1:] for i, p in enumerate(pal))

def _alias_final(seg):
    """Comunidad/provincia con la que termina el segmento ('Amurrio Alava' -> 'alava'); no si va seguida de más palabras
    (así 'Valencia de Alcántara' o 'Las Palmas de Gran Canaria' siguen siendo localidades)."""
    m = re.search(r"(?<![a-z0-9])(" + "|".join(re.escape(a) for a in _ALIAS) + r")$", _plano(seg))
    return m.group(1) if m else None


def lugar_general(texto):
    """'C/ Sol s/n 18197 Pulianas - GRANADA' -> 'Pulianas'. Quita calle, número, código postal y recinto y deja la
    localidad; si no aparece ninguna, la provincia o comunidad que figure; si solo hay un recinto, queda vacío."""
    t = re.sub(r"\((?:ESP|Spain)\)|\b(?:Espanya|España|Spain)\b", " ", texto or "", flags=re.IGNORECASE)
    restos = []
    for seg in _RE_SEP.split(t):
        seg = seg.strip(" .\t\"“”'·")
        if not seg:
            continue
        nums = list(_RE_NUM.finditer(seg))
        if nums:  # número de calle o código postal: lo que sigue es la localidad
            seg = re.sub(r"^(?:de|en)\s+", "", seg[nums[-1].end():].strip(" .-"), flags=re.IGNORECASE)
            if not seg:
                continue
        if _RE_VIA.match(_plano(seg)):
            continue
        restos.append(seg)
    localidades, solo_alias = [], []
    for seg in restos:
        a = _alias_final(seg)
        if not a:
            localidades.append(seg)
        elif _plano(seg) == a:
            solo_alias.append(a)  # el segmento es solo una provincia o comunidad
        else:  # 'Amurrio Alava' -> 'Amurrio'; pero 'Priego de Córdoba' se queda como está
            base = seg[: len(seg) - len(a)].rstrip(" .-") if len(_plano(seg)) == len(seg) else seg
            ultima = base.split()[-1].lower() if base.split() else ""
            localidades.append(base if base and ultima not in _PARTICULAS else seg)
    if localidades:
        return _titulo(localidades[-1])
    if solo_alias:  # sin localidad: lo primero que se citó (lo más específico)
        return {**PROVINCIAS, **COMUNIDADES}[solo_alias[0]]
    return ""


def partes_celda(td):
    """Textos de una celda sin duplicados (el listado repite datos para la vista móvil)."""
    partes = []
    for t in td.stripped_strings:
        t = re.sub(r"^(Location|Updated):\s*", "", norm(t))
        if t and t not in partes:
            partes.append(t)
    return partes


def iso_fechas(fecha, anio=ANIO):
    """'31 Oct - 1 Nov' / '24-25 Oct' / '1 Nov' -> ('2026-10-31', '2026-11-01')."""
    f = norm(fecha)
    patrones = [
        (r"(\d{1,2}) ([A-Za-z]{3}) ?- ?(\d{1,2}) ([A-Za-z]{3})", lambda g: (g[0], g[1], g[2], g[3])),
        (r"(\d{1,2}) ?- ?(\d{1,2}) ([A-Za-z]{3})", lambda g: (g[0], g[2], g[1], g[2])),
        (r"(\d{1,2}) ([A-Za-z]{3})", lambda g: (g[0], g[1], g[0], g[1])),
    ]
    for pat, orden in patrones:
        m = re.fullmatch(pat, f)
        if m:
            d1, m1, d2, m2 = orden(m.groups())
            if m1.capitalize() in MESES and m2.capitalize() in MESES:
                a1, a2 = anio, anio + (1 if MESES[m2.capitalize()] < MESES[m1.capitalize()] else 0)
                return (f"{a1}-{MESES[m1.capitalize()]:02d}-{int(d1):02d}", f"{a2}-{MESES[m2.capitalize()]:02d}-{int(d2):02d}")
    return "", ""


def fila_competicion(tid, tr, anio=ANIO):
    """Una fila del listado: [iconos] código/nombre | organizador | lugar | fecha | actualizado.
    Se localizan las columnas desde la derecha (fecha seguida de 'actualizado'), porque en algunos años la fila
    lleva celdas vacías delante y el número de celdas no es siempre el mismo."""
    celdas = tr.find_all("td", recursive=False)
    textos = [partes_celda(td) for td in celdas]
    c = {"toId": tid, "codigo": "", "competicion": "", "organizador": "", "lugar": "", "fecha": "", "actualizado": ""}
    k = next((i for i in range(2, len(textos) - 1)
              if re.fullmatch(RE_FECHA, " ".join(textos[i])) and re.fullmatch(RE_ACT, " ".join(textos[i + 1]))), None)
    if k is not None:
        c["fecha"], c["actualizado"] = " ".join(textos[k]), " ".join(textos[k + 1])
        c["lugar"] = " ".join(textos[k - 1])
        c["organizador"] = " / ".join(textos[k - 2])
        izq = []
        for cell in textos[: k - 2]:  # código y nombre (el nombre se repite para la vista móvil)
            izq += [t for t in cell if t not in izq]
        if izq:
            c["codigo"], c["competicion"] = izq[0], " ".join(izq[1:])
    elif len(celdas) >= 5:
        comp = textos[0]
        c["codigo"], c["competicion"] = (comp[0], " ".join(comp[1:])) if comp else ("", "")
        c["organizador"] = " / ".join(textos[1])
        c["lugar"] = " ".join(textos[2])
        c["fecha"] = " ".join(textos[3])
        c["actualizado"] = " ".join(textos[4])
    # comprobación/respaldo: fecha y actualización son lo último de la fila
    texto = " ".join(t for t in (norm(x) for x in tr.stripped_strings) if not re.match(r"(Location|Updated):", t))
    m = re.search(RE_FECHA + r"\s+" + RE_ACT + r"\s*$", texto)
    if m and (not c["fecha"] or not re.fullmatch(RE_FECHA, c["fecha"])):
        c["fecha"], c["actualizado"] = m.group(1), m.group(2)
    if not c["competicion"]:
        c["competicion"] = texto
    c["fecha_inicio"], c["fecha_fin"] = iso_fechas(c["fecha"], anio)
    c["lugar_original"], c["lugar"] = c["lugar"], lugar_general(c["lugar"])
    return c


def listar_competiciones(debug=False):
    """Competiciones de todos los años (del más reciente al más antiguo, para que lo nuevo se procese primero)."""
    comps = {}
    Path("debug").mkdir(exist_ok=True)
    for anio in range(date.today().year, PRIMER_ANIO - 1, -1):
        try:
            r = S.get(LIST_URL.format(anio=anio), timeout=60)
        except requests.RequestException as e:
            print(f"Listado {anio}: error de red ({e}); se omite en esta ejecución", file=sys.stderr)
            continue
        html = r.text
        soup = BeautifulSoup(html, "lxml")
        Path(f"debug/listado_{anio}.html").write_text(html, encoding="utf-8")
        n = 0
        for tr in soup.find_all("tr"):
            if tr.find("tr"):
                continue
            m = re.search(r"toId=(\d+)", str(tr))  # busca en href, onclick, data-*...
            if m and m.group(1) not in comps:
                comps[m.group(1)] = fila_competicion(m.group(1), tr, anio)
                n += 1
        print(f"Listado {anio}: HTTP {r.status_code}, {len(html)} caracteres, {n} competiciones")
        time.sleep(PAUSE)
    if not comps:
        sys.exit("Los listados no contienen competiciones: ¿bloqueo o HTML distinto? Mira debug/listado_<año>.html")
    for c in ([] if debug else list(comps.values())[:2]):
        print("  ejemplo del listado:", {k: c[k] for k in ("toId", "codigo", "competicion", "lugar_original", "lugar", "fecha", "actualizado")})
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


def atletas_club_enc(html):
    """Atletas del club en el listado de participantes por País/Aut./Club (ENC.php): el listado agrupa
    a los inscritos por club bajo una cabecera "2138 - CDE ARQUEROS DE POZUELO". Se excluyen los técnicos."""
    soup = BeautifulSoup(html, "lxml")
    nombres, en_club = set(), False
    for tr in soup.find_all("tr"):
        if tr.find("tr"):
            continue
        llenas = [c for c in (norm(x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])) if c]
        if len(llenas) == 1:  # cabecera de grupo (club o comunidad)
            en_club = bool(CLUB_RE.search(llenas[0]))
        elif en_club and len(llenas) >= 3 and not any("cnico" in c for c in llenas):
            nombres.add(llenas[0])
    return nombres


def filas_club(codigo, html, nombres=(), enc=()):
    """Filas del club en una página de resultados, con la sección en la que aparecen.
    - Individuales (I*): filas que mencionan al club (código 2138, POZUE o nombre) o cuyo atleta figura
      entre los inscritos del club (enc). Esto último cubre los campeonatos de España, donde la
      clasificación va por comunidades autónomas y no por clubes.
    - Equipos (T*): el nombre del equipo no incluye el código del club (p. ej. "RH102 - Arcopozuelo A")
      y en los campeonatos por comunidades ni siquiera es del club ("MAD - Madrid"): se reconocen por los
      nombres de los atletas del club ya encontrados en la competición."""
    es_equipo = codigo.startswith("T")
    if not es_equipo and not enc and not CLUB_RE.search(html):
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
            cuenta = sum(1 for n in nombres if n in texto)
            autonomico = len(celdas) > 1 and re.match(r"^[A-Z]{3} - ", celdas[1])
            ok = bool(CLUB_RE.search(texto)) or cuenta >= (MIN_AUTONOMICO if autonomico else MIN_MIEMBROS)
        else:
            ok = bool(CLUB_RE.search(texto)) or (len(celdas) > 1 and celdas[1] in enc)
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


def _plano(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").lower()


GENEROS = {"hombre": "Hombre", "hombres": "Hombre", "masculino": "Hombre", "men": "Hombre", "male": "Hombre",
           "mujer": "Mujer", "mujeres": "Mujer", "femenino": "Mujer", "women": "Mujer", "female": "Mujer",
           "mixto": "Mixto", "mixed": "Mixto"}
# sistema español -> sistema internacional (es la misma categoría)
EDADES = {"menor": "Sub 15", "menores": "Sub 15", "alevin": "Sub 15", "alevines": "Sub 15",
          "cadete": "Sub 18", "cadetes": "Sub 18", "junior": "Sub 21", "juniors": "Sub 21",
          "veterano": "Plus 50", "veteranos": "Plus 50"}


def normalizar_categoria(cat, es_equipo=False):
    """Unifica mayúsculas/minúsculas y equivalencias. Devuelve (categoria, genero).
    Individual: el género va al final. Equipos: solo se unifica el género y se respeta el resto."""
    resto, genero = [], ""
    for p in norm(cat).split():
        k = _plano(p)
        if k in GENEROS:
            genero = GENEROS[k]
            if es_equipo:
                resto.append(genero)
            continue
        if not es_equipo:
            m = re.fullmatch(r"(?:u|sub)-?(\d{2})", k)
            if k in EDADES:
                p = EDADES[k]
            elif m:
                p = f"Sub {m.group(1)}"
            elif k in ("sub", "plus"):
                p = k.capitalize()
            elif p.isalpha() and (p.islower() or p.isupper()):
                p = p.capitalize()
        resto.append(p)
    if not es_equipo and genero:
        resto.append(genero)
    return " ".join(resto), genero


def limpiar_fila(f):
    f["categoria"], f["genero"] = normalizar_categoria(f.get("categoria", ""), f.get("tipo") == "Equipos")
    d = (f.get("division") or "").strip()
    f["division"] = d[:1].upper() + d[1:]
    if f.get("tipo") != "Equipos":  # todas las filas son del club; el nombre cambia según el año ("Arqueros De Pozuelo", "Cde ...")
        f["club"] = CLUB_NOMBRE


def procesar(tid, nombre, fp_anterior, todas, debug=False):
    url = f"{BASE}Details.php?toId={tid}"
    html = get(url)
    if not html:
        return None, None
    soup = BeautifulSoup(html, "lxml")
    # huella: todos los enlaces a TourData (los PDF llevan ?time=... y cambian al actualizarse)
    huella = hashlib.md5((VERSION_DATOS + "|" + "|".join(sorted(a["href"] for a in soup.find_all("a", href=True) if "TourData" in a["href"]))).encode()).hexdigest()
    if huella == fp_anterior and not debug:
        return huella, None
    img = soup.select_one('img[src*="Header/topleft"]')
    if img and img.get("alt") and not nombre:
        nombre = norm(img["alt"])
    filas = []
    if debug:
        d = Path("debug") / tid
        d.mkdir(parents=True, exist_ok=True)
        (d / "Details.html").write_text(html, encoding="utf-8")
    todas_pag = paginas_resultados(tid, soup, url, True)
    paginas = [p for p in todas_pag if todas or p[0].startswith(PAGINAS_BASE)]
    if debug:
        print(f"  Páginas de resultados en Details.php: {[p[0] for p in todas_pag] or 'ninguna'}; "
              f"se descargan: {[p[0] for p in paginas] or 'ninguna'}")
    previas = {p[0]: p for p in todas_pag if p[0].startswith(("IQ", "TQ"))}  # clasificación previa (IQRM, TQRM2...)
    cache_q = {}
    enc = set()  # atletas del club según el listado de inscritos (ENC.php), solo en pruebas con clasificación final IF*/TF*
    if any(p[0].startswith(("IF", "TF")) for p in paginas):
        enlace = next((urljoin(url, a["href"]) for a in soup.find_all("a", href=True)
                       if a["href"].endswith("/ENC.php") and f"/{tid}/" in urljoin(url, a["href"])), None)
        he = get(enlace) if enlace else None
        if he:
            if debug:
                (Path("debug") / tid / "ENC.html").write_text(he, encoding="utf-8")
            enc = atletas_club_enc(he)
            if debug:
                print(f"  Listado de inscritos (ENC): {len(enc)} atletas del club")

    def puntos_previos(codigo_final, es_equipo):
        """Puntos de la ronda de clasificación de la misma prueba: IFRM -> IQRM, TFRM2 -> TQRM2."""
        cq = ("TQ" if es_equipo else "IQ") + codigo_final[2:]
        if cq not in previas:
            return {}
        if cq not in cache_q:
            mapa, hq = {}, get(previas[cq][2])
            if hq:
                if debug:
                    (Path("debug") / tid / f"{cq}.html").write_text(hq, encoding="utf-8")
                for celdas, _ in filas_club(cq, hq, nombres, enc):
                    campos, resto = separar(celdas, es_equipo)
                    clave = (campos["equipo_codigo"], campos["equipo"]) if es_equipo else campos["atleta"]
                    mapa[clave] = puntuaciones(resto)["puntos_totales"]
            cache_q[cq] = mapa
        return cache_q[cq]

    paginas.sort(key=lambda p: p[0].startswith("T"))  # primero las individuales
    nombres = set(enc)
    for codigo, evento, href in paginas:
        es_equipo = codigo.startswith("T")
        if es_equipo and not nombres:
            continue  # sin atletas individuales del club no puede haber equipos del club
        h = get(href)
        if not h:
            continue
        if debug:
            (Path("debug") / tid / f"{codigo}.html").write_text(h, encoding="utf-8")
        mapa_q = puntos_previos(codigo, es_equipo) if codigo.startswith(("IF", "TF")) else {}
        for celdas, seccion in filas_club(codigo, h, nombres, enc):
            campos, resto = separar(celdas, es_equipo)
            if not es_equipo and campos["atleta"]:
                nombres.add(campos["atleta"])
                if not CLUB_RE.search(" ".join(celdas)):  # clasificación por comunidades: el club sale del listado de inscritos
                    campos["club_codigo"], campos["club"] = "2138", CLUB_NOMBRE
            division, categoria = dividir(seccion or evento)
            clave = (campos["equipo_codigo"], campos["equipo"]) if es_equipo else campos["atleta"]
            fila = {
                "toId": tid, "competicion": nombre, "codigo_pagina": codigo,
                "tipo": "Equipos" if es_equipo else "Individual", "evento": evento,
                "division": division, "categoria": categoria,
                "puntos_clasificacion": mapa_q.get(clave, ""),
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
    ap.add_argument("--max-minutos", type=float, help="parar de forma ordenada tras estos minutos (por defecto 324)")
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    inicio = time.time()
    tope = args.max_minutos * 60 if args.max_minutos else MAX_SEGUNDOS

    comps = listar_competiciones(bool(args.debug))
    if args.debug:
        c = comps.get(args.debug)
        if c:
            print(f"Competición {args.debug}: {c['competicion']} | {c['fecha_inicio']} a {c['fecha_fin']} | "
                  f"{c['lugar_original']} -> lugar: {c['lugar']!r}")
        else:
            print(f"Competición {args.debug}: NO aparece en los listados de {PRIMER_ANIO} a {date.today().year} "
                  f"(¿no es de España, no está completada o es de otro año?); se prueba igualmente.")
        comps = {args.debug: c or {"toId": args.debug, "competicion": ""}}
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    nac, reg = leer_csv(NAC_CSV), leer_csv(REG_CSV)
    previas = {r["toId"]: r for r in leer_csv(COMP_CSV)}
    revisadas = set()
    hoy = date.today()
    antiguas = (hoy - timedelta(days=DIAS_REVISION)).isoformat()
    pendientes = [t for t in comps if t not in state]
    print(f"{len(comps)} competiciones en los listados, {len(pendientes)} sin descargar todavía")

    def guardar():
        for r in nac + reg:  # fecha y lugar en todas las filas (también las antiguas) y categorías unificadas
            c = comps.get(r["toId"])
            if c:
                r["fecha_inicio"], r["fecha_fin"], r["lugar"] = c["fecha_inicio"], c["fecha_fin"], c["lugar"]
            limpiar_fila(r)
        for rows in (nac, reg):  # competiciones de más reciente a más antigua; dentro, por división, categoría y posición
            rows.sort(key=lambda r: (r.get("division", ""), r.get("categoria", ""),
                                     int(r["posicion_final"]) if r.get("posicion_final", "").isdigit() else 10**9))
            rows.sort(key=lambda r: (r.get("fecha_inicio", ""), int(r["toId"])), reverse=True)
        cuenta = Counter(r["toId"] for r in nac + reg)
        escribir_csv(COMP_CSV, [
            dict(c, url=f"{BASE}Details.php?toId={t}", filas_club=cuenta.get(t, 0),
                 ultima_revision=hoy.isoformat() if t in revisadas else previas.get(t, {}).get("ultima_revision", ""))
            for t, c in comps.items()], COLS_COMP)
        escribir_csv(NAC_CSV, nac, COLS_NAC)
        escribir_csv(REG_CSV, reg, COLS_REG)
        STATE.write_text(json.dumps(state, indent=1))

    for i, (tid, c) in enumerate(comps.items(), 1):
        if time.time() - inicio > tope:
            print("Tiempo máximo alcanzado: lo que falta se descargará en la siguiente ejecución.")
            break
        est = state.get(tid) or {}
        if isinstance(est, str):  # formato antiguo: solo la huella
            est = {"h": est}
        if (not args.debug and est.get("h") and est.get("v") == VERSION_DATOS and est.get("a") == c.get("actualizado", "")
                and c.get("fecha_fin") and c["fecha_fin"] < antiguas):
            continue  # competición terminada hace tiempo y sin cambios en el listado
        huella, filas = procesar(tid, c["competicion"], est.get("h"), args.todas, bool(args.debug))
        if huella is None:
            continue  # fallo de red: se reintentará en la siguiente ejecución
        revisadas.add(tid)
        if filas is not None:
            es_nac = lambda f: f["codigo_pagina"].startswith(("IF", "TF"))
            nac = [r for r in nac if r["toId"] != tid] + [f for f in filas if es_nac(f)]
            reg = [r for r in reg if r["toId"] != tid] + [f for f in filas if not es_nac(f)]
            if filas or args.debug:
                print(f"[{i}/{len(comps)}] {tid} ({c.get('fecha_inicio', '')}): {len(filas)} filas del club")
        if args.debug and filas:
            print(f"  Fecha: {c.get('fecha_inicio', '')} a {c.get('fecha_fin', '')} | Lugar: {c.get('lugar', '')} (original: {c.get('lugar_original', '')})")
            for f in filas:
                f.update(fecha_inicio=c.get("fecha_inicio", ""), fecha_fin=c.get("fecha_fin", ""), lugar=c.get("lugar", ""))
                limpiar_fila(f)
            for f in filas:
                quien = f["miembros"] if f["tipo"] == "Equipos" else f["atleta"]
                nombre = f["equipo"] if f["tipo"] == "Equipos" else f["club"]
                pts = ""
                if f["puntos_totales"] or f.get("puntos_clasificacion"):
                    pts = f" | puntos {f['puntos_totales'] or f['puntos_clasificacion']}"
                print(f"  [{f['codigo_pagina']}] {f['division']} | {f['categoria']} | pos {f['posicion_final']} | {quien} | {nombre}{pts}")
            escribir_csv(Path("debug") / f"filas_{tid}.csv", filas, RES_COLS)
        if not args.debug:
            state[tid] = {"h": huella, "a": c.get("actualizado", ""), "v": VERSION_DATOS}
            if len(revisadas) % 50 == 0:
                guardar()  # guardado parcial: si algo se interrumpe no se pierde el avance

    if args.debug:
        return
    guardar()
    restantes = [t for t in comps if t not in state]
    print("Terminado." if not restantes else f"Quedan {len(restantes)} competiciones sin descargar: vuelve a ejecutarlo para continuar.")


if __name__ == "__main__":
    main()
