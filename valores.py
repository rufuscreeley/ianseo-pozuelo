"""Lista los valores distintos de division y categoria de los CSV, con cuántas filas tiene cada uno."""
import csv, collections

for campo in ("division", "categoria"):
    cuenta = collections.Counter()
    for fichero in ("data/resultados_nacionales.csv", "data/resultados_regionales.csv"):
        with open(fichero, encoding="utf-8", newline="") as f:
            for fila in csv.DictReader(f):
                cuenta[fila[campo]] += 1
    print(campo.upper(), f"({len(cuenta)} valores)")
    for valor, n in sorted(cuenta.items(), key=lambda x: (x[0].lower(), x[0])):
        print(f"  {n:4}  {valor!r}")

print()
print("FILAS INDIVIDUALES SIN DIVISIÓN O SIN CATEGORÍA (por página)")
paginas = collections.Counter()
for fichero in ("data/resultados_nacionales.csv", "data/resultados_regionales.csv"):
    with open(fichero, encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            if fila["tipo"] == "Individual" and (not fila["division"] or not fila["categoria"]):
                paginas[(fila["toId"], fila["competicion"][:45], fila["url"].rsplit("/", 1)[-1], fila["division"], fila["categoria"])] += 1
for (toid, nombre, pagina, div, cat), n in sorted(paginas.items(), key=lambda x: -x[1])[:30]:
    print(f"  {n:3}  {toid}  {pagina:10} div={div!r} cat={cat!r}  {nombre}")
