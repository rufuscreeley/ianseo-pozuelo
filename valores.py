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
