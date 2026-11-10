import collections
import unittest

import scraper


class AgruparNombresTests(unittest.TestCase):
    def test_unifica_las_variantes_explicitas_de_castroseiros(self):
        canonico = "CASTROSEIROS BRIONGOS Mª Eugenia"
        cuenta = collections.Counter({
            "CASTROSEIROS Mª Eugenia": 1,
            "CASTROSEIROS BRIONGO Mº Eugenia": 1,
            "CASTROSEIROS BRIONGOS María Eugenia": 1,
            "CASTROSEIROS M.EUGENIA": 1,
            "CASTROSEIROS Mª Eugenia Lic 87087": 1,
            canonico: 3,
        })

        mapa, ambiguos = scraper.agrupar_nombres(cuenta)

        self.assertEqual(set(mapa), {scraper.norm(n) for n in cuenta})
        self.assertEqual(set(mapa.values()), {canonico})
        self.assertEqual(ambiguos, [])

    def test_unifica_nombre_invertido_y_abreviaturas_de_otros_atletas(self):
        variantes = {
            "HERNANDO MORENO Juan Ignacio",
            "JUAN IGNACIO Hernando Moreno",
        }

        mapa, ambiguos = scraper.agrupar_nombres(collections.Counter(variantes))

        self.assertEqual(set(mapa.values()), {"HERNANDO MORENO Juan Ignacio"})
        self.assertEqual(ambiguos, [])

    def test_unifica_variantes_de_m_eugenia_con_nombre_legal_completo(self):
        variantes = {
            "CASTROSEIROS BRIONGOS Mª Eugenia",
            "CASTROSEIROS BRIONGOS M. EUGENIA",
            "CASTROSEIROS M.EUGENIA",
        }

        mapa, ambiguos = scraper.agrupar_nombres(collections.Counter(variantes))

        self.assertEqual(set(mapa.values()), {"CASTROSEIROS BRIONGOS Mª Eugenia"})
        self.assertEqual(ambiguos, [])

    def test_no_fusiona_apellidos_completos_distintos(self):
        nombres = (
            "CASTROSEIROS PEREZ Mª Eugenia",
            "CASTROSEIROS LOPEZ Mª Eugenia",
        )

        mapa, ambiguos = scraper.agrupar_nombres(collections.Counter(nombres))

        self.assertEqual({mapa[nombre] for nombre in nombres}, set(nombres))
        self.assertEqual(ambiguos, [])


class NormalizarCategoriaTests(unittest.TestCase):
    def test_categoria_de_equipo_run_archery_se_normaliza_a_team_sprint(self):
        categoria = "Run archery " * 25 + "sptx team sprint"
        self.assertEqual(scraper.normalizar_categoria(categoria, es_equipo=True), "Team sprint")

    def test_categoria_repetitiva_de_equipo_3d_se_normaliza_a_equipos_x4(self):
        categoria = "3d " * 28 + "divisiones x4"
        self.assertEqual(scraper.normalizar_categoria(categoria, es_equipo=True), "Equipos x 4")

    def test_no_cambia_categorias_individuales_ni_otras_categorias_de_equipo(self):
        run_archery = "Run archery " * 25 + "sptx team sprint"
        equipos_3d = "3d " * 28 + "divisiones x4"
        self.assertEqual(scraper.normalizar_categoria(run_archery), "Senior")
        self.assertEqual(scraper.normalizar_categoria(equipos_3d), "Senior")
        self.assertEqual(scraper.normalizar_categoria("Sub 21", es_equipo=True), "Sub 21")
        self.assertEqual(scraper.normalizar_categoria("1º división", es_equipo=True), "1ª división")


if __name__ == "__main__":
    unittest.main()
