# Guion — Transcripción y Voces (mi parte)

Dos diapositivas, ~2 minutos en total. Texto pensado para decirse tal cual; los **destacados** son las palabras que conviene apoyar con la mano o el puntero.

# Diapositiva 0 · El vídeo (~40 segundos, hablas ENCIMA del vídeo)

*Sincronizado a los tres momentos. No leas: mira la pantalla con el público y señala.*

**[Arranca el vídeo: habla Sánchez — la transcripción aparece con su nombre]**
«Esto que veis es el sistema trabajando en directo: transcribe lo que se dice… y sabe **quién** lo dice. Ahí está Sánchez.»

**[Cambia a Feijóo — el nombre cambia solo]**
«Cambia el orador… y el sistema lo sigue. **Nadie ha tocado nada**: lo reconoce por la voz.»

**[Hablan los dos A LA VEZ]**
«Y ahora la parte importante: hablan los dos a la vez. ¿Qué hace el sistema? **No adivina.** Marca el cruce y lo deja para la revisión humana. Este sistema prefiere un hueco honesto a una atribución inventada — y esa regla gobierna todo lo que os voy a contar.»

**[Fin del vídeo → transición a tu primera diapositiva]**
«¿Cómo funciona esto por dentro? Dos piezas: transcripción y voces.»

# Apertura alternativa (si NO hay vídeo, 10 segundos)

«Mi parte es la base de todo el sistema: convertir el vídeo del pleno en **texto con marca de tiempo**, y saber **quién dijo cada cosa**.»

# Diapositiva 1 · Transcripción (~50 segundos)

«Partimos del vídeo de YouTube del pleno: se descarga y nos quedamos con el audio.

Transcribimos con **Whisper large-v3-turbo cuantizado a 8 bits**. Lo elegimos con una comparativa medida, no a ojo: da la **misma fidelidad que el modelo grande completo** pero es el **triple de rápido** — un pleno de 3 horas se transcribe en unos 10 minutos — y cuantizado **cabe en una GPU doméstica de 4 GB**. Detalle importante para nuestros ayuntamientos: la detección de idioma es **por intervención**, no por vídeo — un pleno puede saltar de castellano a valencià y cada intervención sale en su idioma real.

Whisper transcribe muy bien el castellano… pero **no conoce los nombres del pueblo**: pedanías, partidas, siglas locales. Reentrenarlo lo probamos y no compensa. Lo que sí funciona: un **glosario municipal** — un fichero de texto que se crea al dar de alta el municipio — que corrige esos términos sobre el texto, con sustituciones seguras.

El resultado no es solo texto: es texto donde **cada frase sabe su segundo**. Esa marca de tiempo es lo que después permite saltar al minuto exacto del vídeo desde el buscador o desde el correo de las alertas.»

# Diapositiva 2 · Voces (~50 segundos)

«Segunda mitad: ¿quién dijo cada cosa?

Primero, la **diarización** — pyannote — separa el audio en voces **anónimas**: voz 1, voz 2, voz 3. Todavía sin nombres.

Los nombres llegan por la **huella de voz**: en el registro, cada cargo público —con su conocimiento— deja una huella que no es audio, es un **vector de 192 números**, borrable cuando quiera. Cada voz del pleno se compara con las huellas por **similitud coseno**, y solo se asigna un nombre si supera un umbral. Y aquí nuestra regla de oro: **si no hay huella, la voz queda sin nombre — este sistema nunca adivina una identidad**.

Y el cierre es humano: la persona que levanta acta tiene un **editor con reproductor** — escucha cada voz, confirma el nombre, y el acta **se regenera** sola. La máquina prepara el trabajo; la última palabra es de la secretaría.

Y fijaos en la flecha discontinua: cada voz confirmada **se guarda como huella nueva** — así el siguiente pleno se atribuye solo, por similitud de coseno. **El sistema aprende entre sesiones**: la secretaría trabaja cada vez menos.»

# Cierre (10 segundos)

«Con esto tenemos el acta con quién dijo qué y cada frase anclada al segundo de vídeo — la pieza sobre la que se montan la búsqueda, las alertas y el resto que os van a contar mis compañeros.»

---

# Chuleta · cifras que debes saberte (por si las piden)

| Cifra | Valor |
|---|---|
| Velocidad ASR | 18,4× tiempo real (pleno de 3 h ≈ 10 min) |
| Fidelidad turbo int8 vs large-v3 completo | 88,0 % vs 87,9 % literal (igual) — y 3× más rápido |
| Precisión contra patrón oro verbatim propio | 96,1 % (error de palabra 3,9 %) |
| Palabras literales vs Diarios oficiales, a ciegas | 88 % de media · Madrid 85,3 % |
| Separación de voces (pleno completo del Congreso) | 22 de 22 oradores, correspondencia perfecta |
| Identificación por huella (pleno municipal real) | pureza 100 %, 0 falsos positivos, 92 tramos |
| Huella de voz | vector de 192 dimensiones (ECAPA-TDNN), no audio |
| Auto-aprendizaje entre plenos | 5 de 6 voces sugeridas correctamente al 2º pleno |
| Coste por pleno | 0 € (solo electricidad) |

# Chuleta · preguntas probables y respuesta de 15 segundos

**«¿Por qué no comparáis con el WER estándar contra el Diario oficial?»**
Porque el Diario no es literal: los taquígrafos corrigen y pulen. Compararnos con él mediría la diferencia entre hablar y redactar. Por eso hicimos un patrón oro verbatim propio (ahí sí: 96,1 %) y además medimos palabras literales contra Diarios reales a ciegas (88 %).

**«¿Por qué no afináis Whisper para cada municipio?»**
Lo medimos: el error en términos locales apenas baja afinando y cada municipio necesitaría su modelo. El glosario municipal cuesta un fichero de texto de 10 líneas y cero GPU — y es transferible a cualquier ayuntamiento en el alta.

**«¿Y si el glosario corrige de más?»**
Solo hay dos mecanismos y ambos son conservadores: alias exactos de errores conocidos (riesgo cero) y parecido de cadenas con umbral 0,90 en palabra suelta. El emparejamiento fonético agresivo lo probamos y lo descartamos con datos: rompía frases comunes.

**«¿Cómo sabéis que la huella no se equivoca de persona?»**
Solo asigna nombre por encima de un umbral de similitud; por debajo, la voz queda sin identificar. Medido en un pleno real: pureza del 100 % y cero falsos positivos. Y siempre hay revisión humana con reproductor antes del acta final.

**«¿Eso de las huellas es legal / RGPD?»**
Se registra a cargos públicos con su conocimiento; lo almacenado es un vector matemático, no el audio; es borrable; y no sale del equipo del ayuntamiento. Y la alternativa especulativa (deducir nombres por el contexto) está desactivada por diseño.

**«¿Qué pasa si dos personas hablan a la vez?» (la pregunta del vídeo)**
Tres cosas. (1) El texto se atribuye a la voz PREDOMINANTE — la que más solapa en el tiempo con la frase. (2) Si un segundo orador está activo más del 30 % del segmento, se marca como cruce y el acta lo señala con la misma convención del Diario de Sesiones real: «(Cruce de intervenciones.)». (3) Esos tramos se excluyen del cálculo de huellas, para que una discusión no contamine los vectores de voz. ¿Separar las dos voces de una sola pista? Existe como investigación (separación de fuentes), pero no es fiable en producción — preferimos la honestidad del taquígrafo.

**«¿Y si el ayuntamiento no tiene GPU?»**
Funciona en CPU como proceso nocturno. Con una GPU doméstica de 4 GB va en tiempo casi real de trabajo (10 min por pleno de 3 h).

**«¿El valenciano lo lleva bien?»**
Sí: la detección de idioma es por intervención, así que los plenos bilingües salen cada tramo en su idioma. Y la búsqueda es multilingüe: preguntas en castellano y encuentra lo dicho en valencià.

**«¿Por qué int8 y no el modelo completo?»**
Cuantizar a 8 bits divide la memoria (~1,5 GB) sin pérdida medible de fidelidad en nuestro caso: 88,0 % vs 87,9 %. Es lo que permite que todo corra en un portátil normal — y que el coste por pleno sea cero.

**«¿La huella funciona si se registra por WhatsApp?»**
Medido: no fiable — el embedding mezcla voz y canal de grabación, y un canal distinto baja la similitud a zona ambigua. La regla operativa es enrolar con el micrófono del salón de plenos. Lo tenemos documentado como límite.
