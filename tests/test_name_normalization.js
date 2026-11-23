const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const { agruparNombres } = require("../name-normalization.js");
const { filtrarMedallas, contarMedallas, rankingTop3, categoriaReciente, medallasAtleta } =
  require("../medallistas-ranking.js");

const alias = JSON.parse(fs.readFileSync(path.join(__dirname, "../data/alias_atletas.json"), "utf8"));

test("groups all known Castro-S(e)iros name variants under the canonical spelling", () => {
  const variants = [
    "CASTROSEIROS BRIONGOS Mª Eugenia",
    "CASTROSEIROS BRIONGOS María Eugenia",
    "CASTROSEIROS M.EUGENIA",
    "CASTROSEIROS Mª Eugenia Lic 87087"
  ];
  const { mapa } = agruparNombres(new Map(variants.map(n => [n, 1])), alias);
  assert.deepEqual(new Set(variants.map(n => mapa.get(n))), new Set(["CASTROSEIROS BRIONGOS Mª Eugenia"]));
});

test("groups reversed names but preserves distinct full surnames", () => {
  const variants = ["HERNANDO MORENO Juan Ignacio", "JUAN IGNACIO Hernando Moreno"];
  const distinct = ["DÍEZ BARRA Rafael", "DIAZ BARRA Rafael"];
  const { mapa } = agruparNombres(new Map([...variants, ...distinct].map(n => [n, 1])), alias);
  assert.equal(mapa.get(variants[0]), mapa.get(variants[1]));
  assert.notEqual(mapa.get(distinct[0]), mapa.get(distinct[1]));
});

const resultadosMedallas = [
  { atleta: "ATLETA Uno", fecha_inicio: "2023-05-01", division: "Recurvo", categoria: "Sub 18", genero: "Mujer", posicion_final: "1" },
  { atleta: "ATLETA Uno", fecha_inicio: "2024-06-01", division: "Compuesto", categoria: "Senior", genero: "Mujer", posicion_final: "2" },
  { atleta: "ATLETA Uno", fecha_inicio: "2025-07-01", division: "Recurvo", categoria: "Veterano", genero: "Mujer", posicion_final: "3" },
  { atleta: "ATLETA Dos", fecha_inicio: "2024-04-01", division: "Recurvo", categoria: "Senior", genero: "Hombre", posicion_final: "1" },
  { atleta: "ATLETA Dos", fecha_inicio: "2025-08-01", division: "Recurvo", categoria: "Veterano", genero: "Hombre", posicion_final: "1" },
  { atleta: "ATLETA Tres", fecha_inicio: "2025-09-01", division: "Recurvo", categoria: "Veterano", genero: "Mujer", posicion_final: "2" }
];

test("counts career medals and returns the athlete latest category by competition date", () => {
  assert.deepEqual(medallasAtleta(resultadosMedallas, "ATLETA Uno", {}), [1, 1, 1]);
  assert.equal(categoriaReciente(resultadosMedallas, "ATLETA Uno"), "Veterano");
});

test("year, division and category filters intersect for medal ranking", () => {
  assert.deepEqual(contarMedallas(filtrarMedallas(resultadosMedallas, { anio: "2025", div: "Recurvo", cat: "Veterano" })),
    [1, 1, 1]);

  assert.deepEqual(rankingTop3(resultadosMedallas, { anio: "2025", div: "Recurvo", cat: "Veterano" }).map(a => [a.nombre, a.m]),
    [["ATLETA Dos", [1, 0, 0]], ["ATLETA Tres", [0, 1, 0]], ["ATLETA Uno", [0, 0, 1]]]);
});

test("year filter counts medals only in that year", () => {
  assert.deepEqual(medallasAtleta(resultadosMedallas, "ATLETA Uno", { anio: "2024" }), [0, 1, 0]);
});

test("division filter counts medals only in that division", () => {
  assert.deepEqual(medallasAtleta(resultadosMedallas, "ATLETA Uno", { div: "Recurvo" }), [1, 0, 1]);
});

test("category filter counts medals only in that category", () => {
  assert.deepEqual(medallasAtleta(resultadosMedallas, "ATLETA Uno", { cat: "Senior" }), [0, 1, 0]);
});

test("gender does not reduce career totals or change medal ranking", () => {
  const sinGenero = rankingTop3(resultadosMedallas, {});
  const conGenero = rankingTop3(resultadosMedallas, { gen: "Mujer" });
  assert.deepEqual(conGenero, sinGenero);
  assert.deepEqual(medallasAtleta(resultadosMedallas, "ATLETA Uno", { gen: "Mujer" }), [1, 1, 1]);
});
