"""Muestra qué nombres de atleta se unificarían (variantes de un mismo nombre) y cuáles son ambiguos. No modifica nada."""
import collections, csv
import scraper

cuenta = collections.Counter()
for fichero in ("data/resultados_nacionales.csv", "data/resultados_regionales.csv"):
    with open(fichero, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["tipo"] == "Individual" and r["atleta"]:
                cuenta[r["atleta"]] += 1

mapa, ambiguos = scraper.agrupar_nombres(cuenta)
grupos = collections.defaultdict(list)
for variante, final in mapa.items():
    grupos[final].append(variante)

print(f"{len(cuenta)} variantes -> {len(grupos)} atletas")
print("\nUNIFICADOS (varias variantes -> nombre final)")
for final, variantes in sorted(grupos.items()):
    if len(variantes) > 1:
        print(f"  {final}\n      <- " + " | ".join(sorted(variantes)))
print("\nAMBIGUOS (no se unifican; ¿cuál es?)")
for nombre, candidatos in ambiguos:
    print(f"  {nombre}  ->  {' o '.join(candidatos)}")
