(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.agruparNombres = api;
})(globalThis, function () {
  const PARTICULAS_APELLIDO = new Set(["de", "del", "la", "las", "los", "y", "i", "da", "do", "dos", "das", "van", "von"]);
  const MARIA = new Set(["mª", "ma", "maria", "mari"]);

  function normalizar(nombre) {
    return String(nombre || "").replace(/\s*\blic\.?\s*\d+\b/gi, " ").replace(/\s+/g, " ").trim();
  }

  function plano(texto) {
    return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  function claveAlias(nombre) {
    return plano(normalizar(nombre)).replace(/[^a-z0-9]/g, "");
  }

  function partir(nombre) {
    const palabras = normalizar(nombre).split(/\s+/);
    let i = 0;
    while (i < palabras.length && palabras[i] === palabras[i].toUpperCase() &&
           palabras[i] !== palabras[i].toLowerCase() && !/[ªº]/.test(palabras[i])) i++;
    return [palabras.slice(0, i), palabras.slice(i)];
  }

  function firma(nombre) {
    const [apellidos, pila] = partir(nombre);
    const ap = apellidos.map(plano).filter(p => !PARTICULAS_APELLIDO.has(p));
    const nombres = pila.map(plano);
    const firmaPila = nombres.filter(p => !MARIA.has(p));
    return [ap, firmaPila.length ? firmaPila : nombres];
  }

  function compatibles(a, b) {
    const [ap1, p1] = a, [ap2, p2] = b;
    if (!ap1.length || !ap2.length || !p1.length || !p2.length || ap1[0] !== ap2[0]) return false;
    if (ap1.length > 1 && ap2.length > 1 && ap1.slice(1).join(" ") !== ap2.slice(1).join(" ")) return false;
    const s1 = new Set(p1), s2 = new Set(p2);
    return [...s1].every(p => s2.has(p)) || [...s2].every(p => s1.has(p));
  }

  function compareTuple(a, b) {
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i];
    return 0;
  }

  function maxBy(values, key) {
    return values.reduce((best, value) => compareTuple(key(value), key(best)) > 0 ? value : best);
  }

  function acentos(texto) {
    return [...texto].filter(c => c.codePointAt(0) > 127).length;
  }

  function agruparNombres(cuenta, gruposAlias = []) {
    const conteo = new Map();
    for (const [nombre, veces] of cuenta instanceof Map ? cuenta : Object.entries(cuenta)) {
      const limpio = normalizar(nombre);
      if (limpio) conteo.set(limpio, (conteo.get(limpio) || 0) + veces);
    }
    const nombres = [...conteo.keys()];
    const firmas = new Map(nombres.map(n => [n, firma(n)]));
    const padre = new Map(nombres.map(n => [n, n]));

    function raiz(nombre) {
      let actual = nombre;
      while (padre.get(actual) !== actual) {
        padre.set(actual, padre.get(padre.get(actual)));
        actual = padre.get(actual);
      }
      return actual;
    }

    function unir(a, b) {
      const ra = raiz(a), rb = raiz(b);
      if (ra !== rb) padre.set(ra, rb);
    }

    const gruposPorClave = new Map();
    gruposAlias.forEach(grupo => {
      [grupo.canonical, ...grupo.aliases].forEach(nombre => gruposPorClave.set(claveAlias(nombre), grupo));
    });
    for (const grupo of gruposAlias) {
      const claves = new Set([grupo.canonical, ...grupo.aliases].map(claveAlias));
      const presentes = nombres.filter(n => claves.has(claveAlias(n)));
      presentes.slice(1).forEach(n => unir(presentes[0], n));
    }

    const completos = nombres.filter(n => firmas.get(n)[0].length >= 2);
    const incompletos = nombres.filter(n => firmas.get(n)[0].length < 2);
    for (let i = 0; i < completos.length; i++) {
      for (const b of completos.slice(i + 1)) {
        if (compatibles(firmas.get(completos[i]), firmas.get(b))) unir(completos[i], b);
      }
    }

    const ambiguos = [];
    for (const nombre of incompletos) {
      const candidatos = new Set(completos.filter(c => compatibles(firmas.get(nombre), firmas.get(c))).map(raiz));
      if (candidatos.size === 1) unir(nombre, [...candidatos][0]);
      else if (candidatos.size > 1) ambiguos.push([nombre, [...candidatos].sort()]);
    }
    const nombresAmbiguos = new Set(ambiguos.map(([n]) => n));
    for (let i = 0; i < incompletos.length; i++) {
      for (const b of incompletos.slice(i + 1)) {
        if (raiz(incompletos[i]) !== raiz(b) && compatibles(firmas.get(incompletos[i]), firmas.get(b)) &&
            !nombresAmbiguos.has(incompletos[i]) && !nombresAmbiguos.has(b)) unir(incompletos[i], b);
      }
    }

    const grupos = new Map();
    for (const nombre of nombres) {
      const r = raiz(nombre);
      if (!grupos.has(r)) grupos.set(r, []);
      grupos.get(r).push(nombre);
    }

    const mapa = new Map();
    for (const miembros of grupos.values()) {
      const apellidos = maxBy(miembros.map(partir).map(p => p[0]), ap => [
        ap.filter(x => !PARTICULAS_APELLIDO.has(plano(x))).length,
        acentos(ap.join(" ")),
        miembros.filter(n => partir(n)[0].join(" ") === ap.join(" ")).reduce((s, n) => s + conteo.get(n), 0)
      ]);
      const pila = maxBy(miembros.map(partir).map(p => p[1]), p => [
        p.length,
        acentos(p.join(" ")),
        miembros.filter(n => partir(n)[1].join(" ") === p.join(" ")).reduce((s, n) => s + conteo.get(n), 0)
      ]);
      const canonicos = new Set(miembros.map(n => gruposPorClave.get(claveAlias(n))?.canonical).filter(Boolean));
      const final = canonicos.size === 1 ? [...canonicos][0] :
        (apellidos.length && pila.length ? [...apellidos, ...pila].join(" ") : maxBy(miembros, n => [conteo.get(n)]));
      miembros.forEach(n => mapa.set(n, final));
    }
    return { mapa, ambiguos };
  }

  return { agruparNombres, normalizar, claveAlias };
});
