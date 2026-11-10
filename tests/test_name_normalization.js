const assert = require("node:assert/strict");
const { test } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const { agruparNombres } = require("../name-normalization.js");

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
