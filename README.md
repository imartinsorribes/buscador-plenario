# Buscador Plenario Inteligente

Convierte el vídeo de un pleno municipal en un **acta consultable**: transcribe,
identifica **quién dijo qué**, permite buscar por temas y saltar al **minuto exacto**, y avisa
a los vecinos de los asuntos que les interesan. Con modelos **locales**, pensado para
ayuntamientos y respetando la protección de datos (RGPD).

Proyecto del **Reto 2** de [IDAL — Intelligent Data Analysis Laboratory](https://www.uv.es/uvweb/servicio-investigacion/es/grupos-investigacion-1285947851930.html?p2=1889),
Escuela Técnica Superior de Ingeniería (ETSE), **Universitat de València**.
Premio al mejor proyecto de todos los retos.

## Demostraciones en vídeo

- **Demo principal** — [Buscador Plenario Inteligente](https://youtu.be/9fzL5NMBZjQ)
- **Ampliación multimodal (SEDIPUALB@)** — [Asistente de manuales](https://youtu.be/HED5Cjro4zM)

## ¿Qué hace?

- **Acta automática** del vídeo del pleno, con cada frase anclada a su segundo.
- **Quién dijo qué** por huella de voz — nunca adivina una identidad.
- **Buscador semántico** en lenguaje natural que cita y enlaza al minuto y al Diario oficial.
- **Alertas para vecinos** por tema (nunca por persona), con la cita y el momento exacto.
- **Asistente de manuales** de administración electrónica, citando manual y página.
- **Modo ciudadano**: diez años de votaciones del Congreso en un mapa de posiciones por tema.

## Cómo funciona

| Bloque | Qué hace | Módulos |
|---|---|---|
| Transcripción | YouTube → audio → texto con marcas de tiempo (faster-whisper large-v3-turbo int8) | `src/download.py`, `src/transcribe.py` |
| Voces | Diarización (pyannote) + huella de voz (ECAPA) con revisión humana | `src/diarize.py`, `src/voiceid.py`, `src/speakers.py` |
| Búsqueda | Fragmentos, embeddings BGE-M3 en ChromaDB, enlace al minuto | `src/index.py`, `src/search.py` |
| Alertas | Catálogo cerrado de temas, correo extractivo con cita y minuto | `src/alertas.py` |
| Manuales | RAG multimodal sobre manuales de SEDIPUALB@ (texto, capturas, vídeo) | `src/manuales.py` |
| Interfaz | Web con reproductor sincronizado | `app/server.py`, `app/index.html` |

## Instalación y uso

Ver **[INSTALL.md](INSTALL.md)** para los requisitos, la instalación y los comandos
para procesar un pleno o dar de alta un ayuntamiento nuevo.

## Documentación

En [`docs/`](docs/) están la memoria técnica, el estudio de costes por modelo y la
documentación de cada bloque (transcripción y voces, alertas, asistente de manuales).

## Equipo

David Puertes Santonja, Narcís Casián Romega, Jorge García Pozuelo e Iñaki Martín Sorribes.

---

<sub>Los datos de los plenos (audio, transcripciones, huellas de voz y bases de datos) no forman
parte de este repositorio: se generan en local y no salen del equipo del ayuntamiento.</sub>
