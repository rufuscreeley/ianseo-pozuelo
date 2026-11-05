"""Scraper de Ianseo: competiciones completadas de España (2026) -> CSV con los
resultados (individuales y por equipos) del club Arqueros de Pozuelo.

Uso:
  python scraper.py                 # ejecución normal (solo procesa lo nuevo o cambiado)
  python scraper.py --debug 28562   # guarda el HTML de una competición en debug/ para revisarlo
  python scraper.py --brackets      # incluye también los cuadros de eliminatorias (IB*/TB*)
"""
import argparse, csv, hashlib, json, re, sys, time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ianseo.net/"
LIST_URL = BASE + "TourList.php?Year=2026&countryid=ESP&comptime=2&timeType=local"
CLUB = "POZUE"  # código del club en Ianseo: "POZUE - Cde Arqueros De Pozuelo"
HEADERS = {"User-Agent": "ArquerosPozuelo-resultados/1.0 (contacto: TU_EMAIL)"}
PAUSE = 1.0  # segundos entre peticiones

DATA = Path("data")
COMP_CSV, RES_CSV, STATE = DATA / "competiciones.csv", DATA / "resultados_pozuelo.csv", DATA / "state.json"
RES_COLS = ["toId", "competicion", "codigo_pagina", "tipo", "evento", "celdas", "contexto", "url", "extraido"]
RESULT_PAGE = re.compile(r"/((?:I|T)[A-Z0-9]{1,4})\.php$")  # IC, IQRM, IFRM, TQRM, TFCX2...

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


def paginas_resultados(tid, soup, url, brackets):
    vistas, out = set(), []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        m = RESULT_PAGE.search(href)
        if not m or f"/{tid}/" not in href or href in vistas:
            continue
        codigo = m.group(1)
        if codigo[:2] in ("IB", "TB") and not brackets:
            continue
        vistas.add(href)
        out.append((codigo, a.get_text(" ", strip=True), href))
    return out


def filas_club(codigo, html):
    """Filas de la página que mencionan al club. En páginas de equipos añade las
    filas siguientes como contexto (los componentes del equipo)."""
    if CLUB not in html:
        return []
    soup = BeautifulSoup(html, "lxml")
    res = []
    for tr in soup.find_all("tr"):
        if tr.find("tr") or CLUB not in tr.get_text():
            continue
        celdas = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if sum(1 for c in celdas if c) < 3:  # descarta filas de detalle de una sola celda
            continue
        contexto = ""
        if codigo.startswith("T"):
            sig = tr.find_next_siblings("tr", limit=3)
            contexto = " || ".join(" | ".join(c.get_text(" ", strip=True) for c in s.find_all(["td", "th"])) for s in sig)
        res.append((celdas, contexto))
    return res


def procesar(tid, nombre, fp_anterior, brackets, debug=False):
    url = f"{BASE}Details.php?toId={tid}"
    html = get(url)
    if not html:
        return None, None
    soup = BeautifulSoup(html, "lxml")
    # huella: todos los enlaces a TourData (los PDF llevan ?time=... y cambian al actualizarse)
    huella = hashlib.md5("|".join(sorted(a["href"] for a in soup.find_all("a", href=True) if "TourData" in a["href"])).encode()).hexdigest()
    if huella == fp_anterior and not debug:
        return huella, None
    filas = []
    if debug:
        d = Path("debug") / tid
        d.mkdir(parents=True, exist_ok=True)
        (d / "Details.html").write_text(html, encoding="utf-8")
    for codigo, evento, href in paginas_resultados(tid, soup, url, brackets):
        h = get(href)
        if not h:
            continue
        if debug:
            (Path("debug") / tid / f"{codigo}.html").write_text(h, encoding="utf-8")
        for celdas, ctx in filas_club(codigo, h):
            filas.append({
                "toId": tid, "competicion": nombre, "codigo_pagina": codigo,
                "tipo": "Equipos" if codigo.startswith("T") else "Individual",
                "evento": evento, "celdas": " | ".join(celdas), "contexto": ctx,
                "url": href, "extraido": date.today().isoformat(),
            })
    return huella, filas


def leer_csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def escribir_csv(path, filas, cols):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", metavar="TOID")
    ap.add_argument("--brackets", action="store_true")
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)

    comps = listar_competiciones(bool(args.debug))
    if args.debug:
        comps = {args.debug: comps.get(args.debug, {"toId": args.debug, "fila": ""})}
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    resultados = leer_csv(RES_CSV)
    nuevas = [t for t in comps if t not in state]
    print(f"{len(comps)} competiciones en el listado, {len(nuevas)} nuevas")

    for i, (tid, c) in enumerate(comps.items(), 1):
        huella, filas = procesar(tid, c["fila"], state.get(tid), args.brackets, bool(args.debug))
        if huella is None:
            continue  # fallo de red: se reintentará el mes siguiente
        if filas is not None:
            resultados = [r for r in resultados if r["toId"] != tid] + filas
            print(f"[{i}/{len(comps)}] {tid}: {len(filas)} filas del club")
        if not args.debug:
            state[tid] = huella

    if args.debug:
        return
    escribir_csv(COMP_CSV, [{"toId": t, "fila": c["fila"]} for t, c in comps.items()], ["toId", "fila"])
    escribir_csv(RES_CSV, resultados, RES_COLS)
    STATE.write_text(json.dumps(state, indent=1))


if __name__ == "__main__":
    main()
