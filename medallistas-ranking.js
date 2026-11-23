(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.medallistasRanking = api;
})(globalThis, function () {
  function posicionMedalla(row) {
    const posicion = parseInt(row.posicion_final, 10);
    return posicion >= 1 && posicion <= 3 ? posicion : null;
  }

  function filtrarMedallas(rows, filtros = {}, opciones = {}) {
    const ignorarGenero = opciones.ignorarGenero !== false;
    const incluirBusqueda = opciones.incluirBusqueda === true;
    const normalizar = opciones.normalizar || (value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase());
    const consulta = normalizar(filtros.q);
    const camposBusqueda = opciones.camposBusqueda || ["atleta"];

    return rows.filter(row =>
      (!filtros.anio || (row.fecha_inicio || "").slice(0, 4) === filtros.anio) &&
      (!filtros.ambito || row.ambito === filtros.ambito) &&
      (!filtros.div || row.division === filtros.div) &&
      (!filtros.cat || row.categoria === filtros.cat) &&
      (ignorarGenero || !filtros.gen || row.genero === filtros.gen) &&
      (!incluirBusqueda || !consulta || camposBusqueda.some(campo => normalizar(row[campo]).includes(consulta)))
    );
  }

  function contarMedallas(rows) {
    const medallas = [0, 0, 0];
    rows.forEach(row => {
      const posicion = posicionMedalla(row);
      if (posicion) medallas[posicion - 1]++;
    });
    return medallas;
  }

  function rankingTop3(rows, filtros = {}) {
    const porAtleta = new Map();
    filtrarMedallas(rows, filtros, { ignorarGenero: true, incluirBusqueda: true }).forEach(row => {
      if (!row.atleta) return;
      const posicion = posicionMedalla(row);
      if (!posicion) return;
      const datos = porAtleta.get(row.atleta) || { nombre: row.atleta, m: [0, 0, 0] };
      datos.m[posicion - 1]++;
      porAtleta.set(row.atleta, datos);
    });
    return [...porAtleta.values()]
      .sort((a, b) => b.m[0] - a.m[0] || b.m[1] - a.m[1] || b.m[2] - a.m[2] ||
        String(a.nombre).localeCompare(String(b.nombre), "es"))
      .slice(0, 3);
  }

  function categoriaReciente(rows, nombre) {
    const participaciones = rows.filter(row =>
      row.atleta === nombre &&
      row.categoria &&
      (row.fecha_inicio || row.fecha_fin)
    );
    if (!participaciones.length) return "";
    return participaciones.reduce((actual, row) => {
      const inicio = row.fecha_inicio || row.fecha_fin || "";
      const inicioActual = actual.fecha_inicio || actual.fecha_fin || "";
      if (inicio !== inicioActual) return inicio > inicioActual ? row : actual;
      const fin = row.fecha_fin || row.fecha_inicio || "";
      const finActual = actual.fecha_fin || actual.fecha_inicio || "";
      return fin > finActual ? row : actual;
    }).categoria;
  }

  function medallasAtleta(rows, nombre, filtros = {}) {
    return contarMedallas(filtrarMedallas(rows.filter(row => row.atleta === nombre), filtros, {
      ignorarGenero: true,
      incluirBusqueda: false
    }));
  }

  return { filtrarMedallas, contarMedallas, rankingTop3, categoriaReciente, medallasAtleta };
});
