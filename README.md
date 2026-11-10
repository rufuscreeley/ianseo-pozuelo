# Resultados de Ianseo · Arqueros de Pozuelo

Este proyecto recopila y publica los resultados de los deportistas del Club Arqueros de Pozuelo en competiciones de tiro con arco celebradas en España desde 2021. Los datos se obtienen de las páginas públicas de [Ianseo](https://www.ianseo.net); no se conecta a una base de datos ni requiere credenciales de Ianseo.

La web permite consultar clasificaciones individuales y por equipos, con filtros por año, competición, ámbito, división, categoría y género. También muestra medallas y los puntos disponibles para cada resultado. El código y los datos están en [rufuscreeley/ianseo-pozuelo](https://github.com/rufuscreeley/ianseo-pozuelo); la publicación se hace con GitHub Pages. La URL efectiva del sitio se muestra en el entorno `github-pages` de la ejecución **Publicar web** de GitHub Actions.

## Alcance y datos

El scraper revisa los listados de competiciones completadas de España de Ianseo desde 2021. Por defecto procesa las páginas de resultados individuales y por equipos (códigos `IF*` y `TF*`) y las clasificaciones por clase y división (`IC`). `--todas` añade páginas de clasificación (`IQ*` y `TQ*`) y cuadros (`IB*` y `TB*`).

Los archivos de `data/` son:

| Archivo | Contenido |
| --- | --- |
| `resultados_nacionales.csv` | Por defecto, resultados individuales y por equipos de páginas `IF*` y `TF*`, incluidos los puntos de clasificación cuando están disponibles. |
| `resultados_regionales.csv` | Por defecto, resultados de páginas `IC`, con puntos totales cuando están disponibles. |
| `competiciones.csv` | Competiciones revisadas, fechas, lugar, enlace a Ianseo y número de filas del club. |
| `alias_atletas.json` | Equivalencias explícitas para nombres de atletas. |
| `meta.json` | Fecha que muestra la web como última actualización. |
| `state.json` | Huellas y estado de descarga que el scraper utiliza para evitar trabajo repetido y reintentar lo pendiente. |

Los CSV están codificados en UTF-8 y llevan una fila de encabezados. Ambos archivos de resultados incluyen competición, fechas, lugar, tipo, división, categoría, género, posición, atleta o equipo, enlace de origen y fecha de extracción; el CSV nacional contiene `puntos_clasificacion` y el regional, `puntos_totales`. La web muestra los puntos disponibles: en resultados nacionales son los de la ronda de clasificación y en los regionales, los puntos totales. Al usar `--todas`, las filas extraídas de páginas distintas de `IF*` y `TF*` también se guardan en el CSV regional.

Los nombres se normalizan mediante reglas conservadoras y las equivalencias de `alias_atletas.json`. Se agrupan variantes compatibles (por ejemplo, diferencias de tildes, orden o abreviaturas), pero se mantienen separados los apellidos completos distintos; las coincidencias ambiguas no se fusionan automáticamente.

`state.json` se guarda junto con los datos del scraper, pero el workflow de publicación lo excluye del sitio desplegado. Los archivos de diagnóstico se escriben en `debug/`, que está ignorado por Git.

## Requisitos

- Python 3.12, la versión usada por los workflows de GitHub Actions.
- Acceso a Internet para consultar Ianseo.
- Para ejecutar los tests JavaScript, Node.js con el módulo integrado `node:test` (Node.js 18 o posterior).

Las dependencias Python están en `requirements.txt`: `requests`, `beautifulsoup4`, `lxml` y `pypdf`.

## Instalación y uso local

Clona el repositorio e instala las dependencias en un entorno virtual. En Windows PowerShell:

```powershell
git clone https://github.com/rufuscreeley/ianseo-pozuelo.git
cd ianseo-pozuelo
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En macOS o Linux, sustituye la creación y activación del entorno virtual por:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Ejecuta el scraper desde la raíz del repositorio:

```bash
python scraper.py
```

La ejecución normal actualiza `data/` de forma incremental. Tiene un límite predeterminado de 324 minutos; si queda trabajo pendiente, puede volver a ejecutarse para continuar. Las competiciones incompletas se reintentan en futuras ejecuciones y sus filas anteriores se conservan.

Opciones disponibles:

```bash
python scraper.py --debug 28562
python scraper.py --todas
python scraper.py --max-minutos 60
```

- `--debug TOID` procesa una competición concreta, fuerza su revisión y guarda las páginas descargadas y las filas encontradas en `debug/`; no actualiza los CSV de producción.
- `--todas` añade a las páginas incluidas por defecto las clasificaciones y los cuadros disponibles en Ianseo.
- `--max-minutos N` cambia el límite de tiempo de la ejecución a `N` minutos. Si no se especifica, el límite es de 324 minutos.

Los scripts auxiliares `nombres.py`, `medallistas.py` y `valores.py` imprimen, respectivamente, variantes y ambigüedades de nombres, los atletas con más medallas y los valores de división/categoría presentes en los CSV. Se ejecutan desde la raíz con `python nombres.py`, `python medallistas.py` o `python valores.py`.

## Actualización y publicación automáticas

El workflow **Actualizar resultados Ianseo** (`.github/workflows/actualizar.yml`) se ejecuta los días 1 y 15 de cada mes a las 05:00 UTC. También puede iniciarse manualmente desde **GitHub → Actions → Actualizar resultados Ianseo → Run workflow**. Cuando hay cambios, guarda los CSV, el estado y la fecha de actualización en `data/` y los publica en `main`.

El workflow **Publicar web** (`.github/workflows/publicar.yml`) despliega el sitio con GitHub Pages después de una actualización correcta, cuando cambian los archivos del sitio en `main`, o al iniciarlo manualmente. Si el scraper detecta fuentes inaccesibles o incompletas, conserva los datos anteriores de esas competiciones y guarda los resultados válidos; aun así, marca la ejecución como fallida, por lo que esa ejecución no activa el despliegue posterior.

Para diagnosticar fuentes, el workflow manual **Depurar Ianseo** ejecuta el modo `--debug` para dos competiciones de muestra y conserva el directorio `debug/` como artefacto descargable.

## Fuentes incompletas y diagnóstico

El scraper prefiere las páginas HTML de resultados. Si una competición solo ofrece un PDF `IC`, comprueba si contiene una tabla de resultados: un PDF que solo contiene la portada vacía no se trata como una fuente incompleta. Si el PDF parece contener resultados pero no se puede procesar, su contenido no se reconoce o falta una página HTML necesaria, la competición se marca como incompleta y se reintenta más adelante; los datos anteriores de esa competición se conservan.

Si una competición no aparece o faltan filas:

1. Comprueba en Ianseo que la competición esté completada y figure en el listado de España.
2. Ejecuta `python scraper.py --debug TOID` con su identificador de competición (`toId`); revisa los mensajes y los archivos creados en `debug/`.
3. Para el proceso automático, consulta el registro de **Actualizar resultados Ianseo** en GitHub Actions. Un resultado fallido puede indicar que quedan fuentes incompletas aunque los datos válidos se hayan guardado.

## Tests

Instala primero las dependencias Python del proyecto. Ejecuta los tests Python de la raíz y de `tests/`, y el test JavaScript de normalización de nombres:

```bash
python -m unittest -v test_scraper
python -m unittest discover -s tests -v
node --test tests/test_name_normalization.js
```
