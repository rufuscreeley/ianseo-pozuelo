# Ianseo Pozuelo

Herramientas y scripts para la gestión, procesamiento y sincronización de datos de competiciones de tiro con arco gestionadas mediante **Ianseo** para el Arqueros de Pozuelo.

---

## 📋 Descripción

Este repositorio contiene utilidades para interactuar con la base de datos y la exportación de resultados del software de gestión de torneos de World Archery, **Ianseo**. El objetivo es facilitar la automatización de listas de participantes, clasificaciones, visualización de eliminatorias y publicación de resultados.

---

## 🎯 Características principales

- **Extracción de datos:** Conexión con bases de datos locales/remotas de Ianseo (MySQL/MariaDB).
- **Procesamiento de resultados:** Parseo y estructuración de puntuaciones en rondas clasificatorias y enfrentamientos directos (*set system*).
- **Exportación flexible:** Generación de resúmenes en formatos limpios (CSV, JSON, PDF o vistas web ligeras).
- **Automatización:** Scripts preparados para actualizar clasificaciones y listas de dianas de forma desatendida durante el desarrollo de la competición.

---

## 🛠️ Requisitos previos

- **Python 3.9+**
- Instancia activa de **Ianseo** (con acceso a su base de datos o volcados de datos)
- Dependencias básicas del entorno:
  - `pandas`
  - `pymysql` / `mysql-connector-python`
  - `openpyxl` (para exportaciones a Excel)

---

## 🚀 Instalación y uso

1. **Clonar el repositorio:**
   ```bash
   git clone [https://github.com/rufuscreeley/ianseo-pozuel.git](https://github.com/rufuscreeley/ianseo-pozuel.git)
   cd ianseo-pozuel
