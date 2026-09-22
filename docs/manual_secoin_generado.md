# SECOIN (Control Interno) — Manual generado del vídeo tutorial

Documento GENERADO automáticamente a partir del vídeo tutorial (https://youtu.be/TO3KMwAOkSE). Cada sección cita el tramo del vídeo del que sale: la fuente es verificable al minuto.

## Introducción y contexto de la herramienta SECOIN

![Captura del vídeo, capítulo 1](data/sedipualba/frames/cap01.png)

SECOIN es el módulo de control interno de la plataforma Sedipualb@, diseñado para facilitar el control económico-financiero encomendado a los funcionarios de intervención en las entidades locales. Su objetivo principal es integrar las funciones de control y gestión con la tramitación administrativa, garantizando la trazabilidad de las actuaciones dentro de los expedientes de SEGES.

### Aspectos clave de la herramienta

* **Ámbito de aplicación:** Aunque está optimizado para entidades que utilizan la gestión de expedientes de Sedipualb@, puede ser utilizado por organizaciones que no dispongan de dicha gestión, si bien con limitaciones en cuanto a la documentación integrada en los expedientes.
* **Origen y base técnica:** La herramienta se desarrolló inicialmente sobre la base de la fiscalización limitada previa de requisitos básicos. Para ello, se utilizaron formularios estandarizados (*checklists*) basados en los de la Diputación de Girona, adaptados y ampliados por un grupo de trabajo de interventoras de la administración local de entidades usuarias de Sedipualb@.
* **Funcionalidades principales:**
  * **Fiscalización de requisitos básicos:** Uso de formularios estandarizados con información adicional integrada.
  * **Gestión de reparos:** Control de los reparos formulados y de su resolución, incluyendo su posterior remisión al Tribunal de Cuentas.
  * **Fiscalización plena:** Emisión de informes de fiscalización plena bajo características similares a los de la fiscalización limitada.

*Fuente: vídeo tutorial, min 0:00–4:02 — https://youtu.be/TO3KMwAOkSE?t=0*

## Módulo SECOIN: Estadísticas de uso y evolución del control interno

![Captura del vídeo, capítulo 2](data/sedipualba/frames/cap02.png)

El módulo SECOIN de Sedipualb@ facilita la gestión y emisión de informes de control interno municipal, estructurándose en torno a la fiscalización previa, el control financiero y la resolución de omisiones de fiscalización. A continuación, se detallan los datos de uso de la plataforma y las fases que componen el ciclo de control:

*   **Fiscalización limitada previa a requisitos básicos:**
    *   Se han emitido un total de **130.648 informes** a través de la plataforma.
    *   Un total de 58 entidades han superado los 50 informes emitidos. Entre ellas, destaca el Consell de Mallorca con casi 28.000 informes, seguido por un grupo de municipios medianos (principalmente de la Comunidad Valenciana y la Región de Murcia, como Picassent, Gilet, Peñíscola, Alaquàs, Manises o San Vicente del Raspeig) que oscilan entre los 500 y los 6.000 informes.
    *   **Distribución por fases de tramitación:**
        *   **Fase O (Reconocimiento de la obligación):** Es la fase con mayor volumen, registrando 46.585 informes.
        *   **Fase AD (Autorización y Disposición):** Registra 28.256 informes.
        *   **Fase A (Autorización):** Registra 25.000 informes.

*   **Informes de control financiero no planificable:**
    *   Implementados a partir de los formularios y modelos de trabajo facilitados por la Diputación de Girona y el Ayuntamiento de Palma de Mallorca.
    *   Actualmente, esta funcionalidad está siendo utilizada por un grupo inicial de entre 15 y 16 entidades.

*   **Informes de omisión de la función interventora:**
    *   Se incorpora este mecanismo para cerrar el ciclo de control, permitiendo la tramitación de expedientes que, por su naturaleza, carecen de un patrón estandarizado y están sujetos a criterios interpretativos.

*Fuente: vídeo tutorial, min 4:02–8:34 — https://youtu.be/TO3KMwAOkSE?t=242*

## Puesta en marcha y configuración inicial de SECOIN

![Captura del vídeo, capítulo 3](data/sedipualba/frames/cap03.png)

El módulo SECOIN (Control Interno Municipal) de Sedipualb@ permite gestionar la fiscalización, el control permanente y la gestión de reparos de las entidades locales. Para comenzar a utilizar la aplicación y realizar la configuración inicial, se deben seguir los siguientes pasos y directrices:

### 1. Alta en el sistema
* **Acceso inicial:** Para acceder, introduzca en el navegador la dirección web de su entidad seguida de `/secoin` (ej. `[url_entidad]/secoin`).
* **Solicitud de alta:** Si su entidad aún no está registrada, el sistema mostrará el mensaje *"Esta entidad no está de alta"*. En este caso, debe abrir un **ticket de soporte** para solicitar el alta.
* **Carga de datos y plantillas:** Tras el alta, el servicio técnico proporcionará la aplicación con plantillas y formularios precargados (ejemplos estándar o cedidos por otras entidades usuarias) para que no tenga que crearlos desde cero.

### 2. Estructura de la aplicación
La herramienta se organiza principalmente en las siguientes secciones:
* **Áreas y Formularios:** Espacio donde se gestionan las plantillas de la aplicación. Las áreas de fiscalización contienen expedientes y, dentro de estos, se encuentran los formularios (actuaciones para fiscalizar).
* **Fiscalizaciones:** Sección para la gestión de fiscalizaciones, reparos, control permanente (control financiero) y omisiones (en fase de pruebas).
* **Configuración y Utilidades:** Permite la exportación de datos y la parametrización del sistema.

### 3. Gestión de Plantillas y Requisitos
Las plantillas de fiscalización se componen de tres tipos de requisitos que pueden editarse o adaptarse:
* **Requisitos básicos y adicionales:** Se configuran definiendo un enunciado y su referencia legal correspondiente.
* **Casilla "Permite no procede":** Al activar esta opción en un requisito, el usuario podrá marcarlo como "No procede" durante la fiscalización, haciendo que el sistema no lo tenga en cuenta para ese caso concreto. Las respuestas posibles para cada requisito son: *Sí*, *No* o *No procede*.

### 4. Configuración de la Numeración Anual (Contadores)
Al iniciar un nuevo año, es común que aparezca un aviso indicando que *"la fecha en la que se está trabajando no coincide con la fecha actual"*. Esto se debe a que la numeración de los informes debe actualizarse manualmente para el nuevo ejercicio.

Para configurar o actualizar los contadores:
1. Acceda a la ventana de **Configuración**.
2. Seleccione el tipo de informe a editar (fiscalizaciones limitadas, fiscalizaciones plenas, reparos o control permanente) y pulse **Editar**.
3. Defina los siguientes campos:
   * **Prefijo:** Texto o año que antecede al número (ej. `2024/FLZ`).
   * **Dígitos:** Cantidad de números que tendrá el contador (ej. 4 dígitos).
   * **Sufijo:** Texto que se añade detrás de la numeración.
   * **Número inicial:** Número por el que comenzará el contador (normalmente `0` al iniciar el año, o el número correlativo correspondiente si se migra desde otra herramienta).

*Fuente: vídeo tutorial, min 8:34–16:02 — https://youtu.be/TO3KMwAOkSE?t=514*

## Configuración de firma, validación y control interno en SECOIN

![Captura del vídeo, capítulo 4](data/sedipualba/frames/cap04.png)

Este apartado describe las opciones de configuración para la generación y firma de informes de fiscalización en el módulo SECOIN, así como los requisitos de validación de plantillas y las particularidades del control financiero permanente.

### Opciones de firma de informes y roles de usuario

*   **Idioma de los informes:** Permite configurar el idioma de generación de los documentos (disponible en español y catalán).
*   **Enviar a firmar automáticamente:** 
    *   **Desmarcado:** El sistema genera un documento en formato `seficu` en estado de borrador, pendiente de envío manual para su firma.
    *   **Marcado:** El documento `seficu` se genera directamente listo para la firma.
*   **Roles en el proceso de fiscalización:**
    *   **Fiscalizador:** Realiza la revisión inicial del formulario. El acceso requiere identificación con certificado de firma electrónica. El sistema registra su identidad en el informe.
    *   **Interventor (Interventor/a o Viceinterventor/a):** Revisa el informe preparado por el fiscalizador y puede aceptarlo, modificarlo o rechazarlo para una nueva fiscalización. Es quien firma el documento final que se incorpora al expediente.
*   **Firma automatizada mediante sello de órgano:** Permite agilizar el proceso firmando el informe a través de un sello de órgano, siempre que se regule y defina como una actuación administrativa automatizada (conforme al artículo 41 de la Ley 40/2015). En este caso, el informe se incorpora directamente al expediente, el cual cambia de estado y muestra el resultado de la última fiscalización realizada.

### Validación de plantillas y Acuerdo de Pleno

*   **Fecha del acuerdo de pleno:** Es un dato obligatorio para la puesta en marcha de la fiscalización limitada previa. Debe indicarse en la configuración, ya que es un requisito legal que se muestra en el informe generado.
*   **Fecha de último pleno (Configuración recomendada):** Permite definir una fecha por defecto para la validación de las plantillas. Al validar múltiples plantillas (cuyo contenido puede variar con el tiempo al añadir requisitos o comprobaciones), el sistema propondrá automáticamente esta fecha, evitando tener que introducirla manualmente en cada una de ellas.

### Control Financiero Permanente

*   **Formularios precargados:** Al igual que en la fiscalización limitada, los formularios para el control financiero permanente no planificable están precargados en el sistema.
*   **Exención de acuerdo de pleno:** A diferencia de la fiscalización limitada previa (exigida por el decreto de control interno), los informes de control permanente no requieren legalmente un acuerdo de pleno para su aprobación o puesta en marcha; pueden ser preparados directamente por el órgano interventor.

*Fuente: vídeo tutorial, min 16:02–21:46 — https://youtu.be/TO3KMwAOkSE?t=962*

## Configuración inicial y gestión de formularios en SECOIN

![Captura del vídeo, capítulo 5](data/sedipualba/frames/cap05.png)

Para poner en marcha el módulo de control interno, la entidad debe gestionar y validar los formularios que se utilizarán en los procesos de fiscalización. El sistema permite adaptar el catálogo disponible a las necesidades reales de cada ayuntamiento antes de comenzar la tramitación.

### Pasos e ideas clave para la puesta en marcha:

* **Selección y aprobación de formularios:**
  * El sistema cuenta con un catálogo extenso (aproximadamente 220 formularios distribuidos por áreas).
  * Se recomienda que cada entidad apruebe y valide únicamente los formularios que vaya a utilizar activamente (por ejemplo, entre 10 y 30), activando otros de manera progresiva según sea necesario.
* **Ubicación de los formularios según el tipo de control:**
  * **Fiscalización previa limitada:** Los formularios se gestionan desde el área general de formularios de la aplicación.
  * **Control financiero / Control permanente no planificable:** Los formularios específicos se encuentran dentro del área denominada por defecto "Control permanente no planificable" (o el nombre personalizado que asigne la entidad).
* **Fases de la integración (SEGRA):**
  1. **Revisión inicial:** Visualizar, aceptar, modificar o sustituir los formularios en el sistema.
  2. **Acuerdo de Pleno:** En el caso específico de la fiscalización limitada, adoptar el acuerdo correspondiente en el Pleno municipal e incorporar dicho documento al sistema.
  3. **Tramitación y firma:** Seleccionar el formulario y firmarlo, ya sea mediante la firma electrónica personalizada del interventor o a través de un sistema de firma de órgano (recomendado para agilizar el proceso cuando existe un volumen elevado de documentos).
* **Explotación de datos:**
  * Toda la información cumplimentada en los formularios se almacena en estructuras de datos que permiten su posterior explotación y generación de informes.
* **Soporte técnico:**
  * Para resolver dudas durante el arranque del sistema, se puede consultar la videoteca de ayuda disponible o solicitar asistencia técnica a través del Centro de Atención al Usuario (CAO).

*Fuente: vídeo tutorial, min 21:46–25:17 — https://youtu.be/TO3KMwAOkSE?t=1306*

## Gestión de Omisiones de la Función Interventora en SECOIN

![Captura del vídeo, capítulo 6](data/sedipualba/frames/cap06.png)

El módulo SECOIN permite registrar, tramitar y emitir los informes de omisión de la función interventora para asegurar que todas las actuaciones de control interno queden integradas en el sistema. Este procedimiento facilita la generación de la documentación necesaria, la recopilación de información del centro gestor y la preparación de los datos requeridos para su posterior remisión al Tribunal de Cuentas (conforme al artículo 28.1 del Real Decreto 424/2017).

### Paso 1: Alta de la omisión y vinculación de expedientes
* **Identificar el expediente de origen:** Introducir en la casilla "expediente origen" el número de expediente de SEGES donde se ha detectado la posible omisión para vincular ambos sistemas.
* **Identificar el centro gestor:** Señalar el área responsable del expediente afectado.
* **Abrir el expediente de resolución:** Crear el expediente específico donde se resolverá la omisión de la función interventora.

### Paso 2: Cumplimentación de datos del gasto (Art. 28.1 RD 424/2017)
Para definir la omisión, se deben rellenar los siguientes campos en la plataforma:
* **NIF y nombre del tercero** afectado.
* **Categoría de la omisión:** Seleccionar si se produjo en una fiscalización previa (limitada o plena) o en una comprobación material de la inversión.
* **Importe estimado** de la fase del gasto omitida.
* **Datos descriptivos del gasto:** Descripción detallada, aplicación presupuestaria, modalidad, naturaleza, tipo de expediente (por ejemplo, contratación), objeto del gasto y observaciones adicionales.

### Paso 3: Configuración de la Diligencia de Apertura y requerimiento al centro gestor
El procedimiento se inicia con una diligencia de apertura donde el órgano interventor comunica la omisión al centro gestor y le requiere una memoria explicativa. 
* **Plantilla de requerimiento:** El sistema precarga una plantilla para solicitar al centro gestor que acredite si las prestaciones se realizaron, justifique por qué no se fiscalizó el expediente, y declare si cabe la devolución del bien o si existen gastos susceptibles de indemnización.
* **Cuerpo de informe adicional:** Se dispone de un campo de texto libre para que el interventor añada requerimientos específicos o información personalizada (útil, por ejemplo, en omisiones de comprobación material).

### Paso 4: Generación y previsualización
* Una vez completados los campos, seleccionar la opción de generar para obtener la **diligencia de apertura** (documento previo al informe definitivo de omisión) y proceder a su previsualización con todos los antecedentes cargados.

*Fuente: vídeo tutorial, min 25:17–41:12 — https://youtu.be/TO3KMwAOkSE?t=1517*

## Cumplimentación del Informe de Omisión de la Función Interventora (Artículo 28)

![Captura del vídeo, capítulo 7](data/sedipualba/frames/cap07.png)

Este apartado describe cómo cumplimentar los campos del informe de omisión de la función interventora en el módulo SECOIN, cuya parametrización está alineada con el artículo 28 del Reglamento de Control Interno y los metadatos requeridos para la remisión de información al Tribunal de Cuentas.

*   **Supuesto de nulidad (Artículo 47 de la Ley 39/2015):** 
    *   Se debe responder obligatoriamente con **Sí** o **No**.
    *   Si se responde **Sí**, el sistema obliga a seleccionar uno o varios motivos de nulidad (prescindencia total del procedimiento, falta de consignación presupuestaria, tramitación de contrato menor improcedente, u otros).
*   **Constatación de las prestaciones realizadas (Apartado C del Artículo 28):** Campo de texto libre para informar sobre la conformidad de la factura o las valoraciones del interventor basadas en la memoria explicativa del centro gestor y el expediente.
*   **Constatación de la existencia de crédito:** Verificación de la disponibilidad de crédito en la aplicación presupuestaria indicada en la diligencia de apertura.
*   **Propuesta de revisión de oficio:** 
    *   Si previamente se marcó que **Sí** existe un supuesto de nulidad, el sistema habilitará la opción de constatar la existencia de incumplimientos normativos que pueden calificar el acto como nulo.
    *   Dispone de un campo de texto libre para la conclusión final del interventor (procedencia de la revisión, pago de indemnización u otra consideración).
    *   Permite registrar como metadato estructurado si finalmente se decide la revisión de oficio o si se informa favorablemente el pago de las facturas por economía procesal u otros motivos (esta opción solo se habilita si se confirmó el supuesto de nulidad).
*   **Órgano competente para adoptar el acuerdo:** Selección del órgano que debe aprobar el acuerdo de continuidad (habitualmente el Presidente/Alcalde, o el Pleno si este fuera el competente para el gasto objeto de omisión).
*   **Reconocimiento Extrajudicial de Créditos (REC):** Indicación de si el expediente requiere aprobación mediante REC para su imputación al presupuesto.
*   **Exigencia de responsabilidades:** Declaración de si la infracción puede derivar en la exigencia de responsabilidades penales o contables.
*   **Ejercicio de generación del gasto:** Especificación de si el gasto omitido corresponde al ejercicio corriente o a ejercicios anteriores.

*Fuente: vídeo tutorial, min 41:12–47:22 — https://youtu.be/TO3KMwAOkSE?t=2472*

## Elaboración y generación del informe de omisión de la función interventora en SECOIN

![Captura del vídeo, capítulo 8](data/sedipualba/frames/cap08.png)

El módulo SECOIN de Sedipualb@ facilita la tramitación y generación del informe de omisión de la función interventora, integrando los requisitos normativos y estructurando la información para su posterior explotación y remisión automatizada.

### Pasos para la cumplimentación y generación del informe

1. **Selección de documentos del expediente:** Al realizar la búsqueda desde el informe de omisión, el sistema accede directamente a los documentos del expediente en tramitación (como la memoria aportada por el centro gestor). Seleccione el documento correspondiente, súbalo y guarde los cambios para actualizar los datos (fecha del informe, etc.).
2. **Estructura del informe (según el artículo 28):** El documento se genera a partir de una plantilla que incluye los siguientes apartados:
   * **Descripción del gasto:** Datos del primer apartado del artículo 28 y fundamentos jurídicos.
   * **Exposición de incumplimientos normativos:** Segundo apartado del artículo 28 (basado en la explicación rellenada previamente) junto con la categorización de los incumplimientos establecida por el Tribunal de Cuentas.
   * **Prestaciones realizadas:** Cuerpo del informe correspondiente al apartado C.
   * **Constatación de la existencia de crédito:** Apartado D.
   * **Revisión de oficio:** Apartado E, donde se informa sobre la procedencia o no de dicha revisión.
   * **Conclusión final:** Incluye un campo de texto libre para que el interventor añada las consideraciones necesarias, además de un texto fijo normativo sobre las responsabilidades e infracciones administrativas derivadas de la omisión.
3. **Confirmación del documento:** Confirme el borrador para generar el documento definitivo e incorporarlo al expediente.

### Utilidades y ventajas del sistema

* **Cumplimiento normativo:** Facilita la elaboración de los informes asegurando que incorporen todo el contenido exigido por la ley.
* **Integración en el control interno:** Incorpora de manera directa toda la información de la omisión en el sistema de control interno municipal.
* **Metadatos y explotación de datos:** El registro de datos estructurados (metadatos) durante la cumplimentación permite analizar y explotar la información a posteriori (por ejemplo, identificar el porcentaje de propuestas de revisión de oficio, la frecuencia de reconocimientos extrajudiciales de crédito o si las omisiones se deben a supuestos de nulidad o anulabilidad).
* **Remisión automatizada:** Permite identificar y utilizar estos metadatos para automatizar el envío de la información requerida al Tribunal de Cuentas.

*Fuente: vídeo tutorial, min 47:22–51:27 — https://youtu.be/TO3KMwAOkSE?t=2842*

## Gestión de Omisiones de la Función Interventora y Control Financiero en SECOIN

![Captura del vídeo, capítulo 9](data/sedipualba/frames/cap09.png)

Este apartado describe los criterios de generación de informes de omisión de la función interventora y las pautas para la implantación del módulo de control financiero no planificable en la plataforma.

### Generación de Informes de Omisión de la Función Interventora
* **Criterio de individualización:** El Tribunal de Cuentas exige que la información de las omisiones se remita de forma individualizada mediante metadatos específicos (causa, motivo, conclusión, proveedor y aplicación presupuestaria).
* **Regla de agrupación:** Se aconseja realizar un informe por cada omisión. Solo se permite la agrupación de varias facturas en un único informe si existe identidad de proveedor, causa y motivo. No se deben agrupar diferentes terceros en un mismo informe, ya que impediría la correcta explotación de los datos (identificación de capítulos o programas presupuestarios afectados).
* **Disponibilidad del módulo:** 
  * El módulo de omisiones no requiere la configuración previa de plantillas ni parametrizaciones por parte del usuario.
  * Está disponible de forma automática para todas las entidades en el entorno de pruebas y se habilita progresivamente en el entorno de producción.

### Implantación del Control Financiero No Planificable
* **Autonomía en la puesta en marcha:** Este módulo depende exclusivamente del interventor. No requiere de un acuerdo formal de la corporación ni de una implantación simultánea de todas las fichas disponibles.
* **Metodología de trabajo recomendada:**
  * **Activación progresiva:** Se aconseja poner en marcha la herramienta de manera gradual, activando las fichas de control (basadas en los modelos de la Diputación de Girona) conforme se vayan necesitando en el trabajo diario.
  * **Carga de plantillas:** A diferencia del módulo de omisiones, para utilizar el control financiero es necesario solicitar al administrador la agregación de las plantillas correspondientes.
* **Características del funcionamiento:**
  * La mecánica de uso es similar al módulo de fiscalización, pero con un carácter más manual: el resultado del informe lo redacta el usuario en lugar de generarse automáticamente en función de respuestas cerradas (sí/no).
  * Permite homogeneizar los criterios de control de la entidad, facilita el relevo entre interventores y simplifica la explotación de datos para la elaboración del informe resumen anual.

*Fuente: vídeo tutorial, min 51:28–70:19 — https://youtu.be/TO3KMwAOkSE?t=3088*

## Buenas prácticas en la cumplimentación de datos y gestión de anexos en SECOIN

![Captura del vídeo, capítulo 10](data/sedipualba/frames/cap10.png)

El módulo SECOIN de Sedipualb@ permite optimizar el control interno municipal simplificando el registro de datos y garantizando la trazabilidad de la documentación. A continuación, se detallan las pautas de trabajo recomendadas por usuarios de la plataforma para flexibilizar el uso de la herramienta y gestionar los documentos anexos de forma eficiente.

### Cumplimentación simplificada de modificaciones presupuestarias
Para evitar una carga de trabajo innecesaria en expedientes con un gran volumen de partidas (como las transferencias de crédito), se recomienda:
* **Registrar solo datos esenciales:** No es necesario transcribir todas las partidas presupuestarias en la herramienta. Se debe cumplimentar únicamente el importe totalizado del aumento y de la minoración.
* **Aprovechar la integración del expediente:** El detalle de las partidas ya consta en la propuesta del expediente concreto. Al enlazar el informe de control permanente con el Código Seguro de Verificación (CSV) de dicha propuesta, queda plenamente identificado el objeto del informe sin necesidad de duplicar la información.

### Métodos para la gestión de documentos anexos
Actualmente, la herramienta no dispone de una función directa para adjuntar anexos dentro del propio formulario. Para aquellos informes que por su trascendencia o por requerimiento de los órganos de tutela deban incorporar cálculos (como los informes de estabilidad de la liquidación, presupuestos, endeudamiento o competencias impropias), se utilizan las siguientes alternativas:

* **Opción 1: Referencia cruzada mediante CSV**
  * Se firma el documento de cálculos o anexo de manera independiente para generar su propio CSV.
  * En el informe generado por la herramienta SECOIN, se hace referencia explícita a dicho CSV en el texto para identificar y vincular ambos documentos de forma inequívoca.

* **Opción 2: Creación de un documento único indisoluble**
  * Se descarga el informe generado por la herramienta SECOIN en formato PDF.
  * Se unifica este PDF con los documentos de cálculos y anexos en un único archivo.
  * Se firma el documento conjunto resultante (por ejemplo, a través de un SÉFICU aparte) para remitirlo como un bloque único al órgano de tutela.

### Trazabilidad y rigor de la información
En la mayoría de los expedientes ordinarios (como las modificaciones de crédito), no es imprescindible fusionar los documentos para garantizar la seguridad jurídica. Al integrarse dentro de un expediente electrónico gestionado por SEGES:
* El sistema registra una bitácora detallada con la fecha, hora, minuto, segundo y usuario que incorpora cada documento.
* El informe emitido queda asociado temporalmente a la documentación exacta que existía en el expediente en ese momento, garantizando la trazabilidad y la imposibilidad de alteración de los antecedentes.

*Fuente: vídeo tutorial, min 70:19–83:51 — https://youtu.be/TO3KMwAOkSE?t=4219*

## Integración de SECOIN con SEGRA y Mejoras en el Proceso de Fiscalización

![Captura del vídeo, capítulo 11](data/sedipualba/frames/cap11.png)

Este apartado describe las recientes mejoras en el módulo SECOIN de la plataforma Sedipualb@, orientadas a agilizar la fiscalización de propuestas de resolución en expedientes gestionados a través de SEGRA (órganos unipersonales) y a facilitar la rectificación de fiscalizaciones limitadas.

### 1. Fiscalización de propuestas de resolución en SEGRA
El proceso de fiscalización se realiza siempre de forma previa a la adopción de decisiones, vinculándose a una propuesta de acuerdo (documento SEFICU) o a una propuesta de resolución (expediente SEGRA). Para agilizar la tramitación en SEGRA se han introducido los siguientes cambios:

* **Identificación del tipo de documento:** Al seleccionar un elemento para fiscalizar, el sistema identifica visualmente si se trata de un documento SEFICU (mostrando su CSV) o de una propuesta SEGRA.
* **Acceso directo para firma:** Cuando se selecciona una propuesta SEGRA, el sistema habilita un enlace directo que redirige al usuario al expediente SEGRA correspondiente.
* **Simplificación del registro:** Desde este enlace, el usuario puede marcar la fiscalización como favorable o desfavorable con un solo clic, evitando tener que navegar y buscar el documento manualmente dentro de la herramienta SEGRA.

### 2. Cancelación y rectificación de fiscalizaciones limitadas
Para subsanar errores en fiscalizaciones ya realizadas, el sistema ofrece alternativas según la acción requerida:

* **Rectificar:** Permite corregir datos generando una nueva ficha de fiscalización basada en el mismo formulario utilizado anteriormente.
* **Cancelar:** Si no se desea utilizar la ficha original y se requiere anular el proceso, se ha incorporado el botón **"Cancelar"**. Al pulsarlo, el sistema muestra las instrucciones necesarias para completar la anulación, que requieren acceder al expediente y cancelar manualmente el documento SEFICU o el informe que se había generado.

### 3. Explotación de datos para informes
La plataforma permite la extracción de la información registrada en el sistema para facilitar el control interno y la elaboración de memorias:

* **Exportación de ficheros:** Los datos contenidos en el módulo son explotables mediante su descarga en formatos estándar como CSV o Excel.
* **Automatización futura:** Se trabaja en el diseño de plantillas (modelos simplificados y estándar) para generar borradores de informes anuales de forma automática, recopilando datos como el número de fiscalizaciones realizadas, sus resultados, omisiones, reparos e informes de control financiero no planificable.

*Fuente: vídeo tutorial, min 83:51–92:56 — https://youtu.be/TO3KMwAOkSE?t=5031*

## Integración de SECOIN con la gestión contable y de contratación

![Captura del vídeo, capítulo 12](data/sedipualba/frames/cap12.png)

El módulo de control interno (SECOIN) de Sedipualb@ se encuentra en proceso de evolución para mejorar la integración entre la gestión administrativa del gasto, la contratación y la contabilidad. A continuación, se detallan los aspectos clave sobre el estado actual y la hoja de ruta de estas integraciones:

* **Registro de datos presupuestarios en fiscalización:** Al elaborar un informe de control financiero o de fiscalización, la plataforma permite incorporar manualmente la partida presupuestaria y el importe. Actualmente, este proceso es informativo; no se trata de un dato que se extraiga automáticamente de la contabilidad ni que se vuelque de forma directa en ella.
* **Hoja de ruta para la integración de contratos y contabilidad:** El objetivo prioritario es conectar la gestión de la contratación con la contabilidad. Se está trabajando para que, en el futuro, los actos y fases administrativas tramitados dentro de la plataforma de contratación (SECA) puedan disparar de forma automática los apuntes contables correspondientes.
* **Gestión unificada de facturas:** Las entidades que utilizan de forma integrada SECA y SEFACE disponen de toda la información relativa al ciclo de vida de las facturas (estado de pago, ubicación y autorizaciones) centralizada dentro del propio sistema Sedipualb@.
* **Compatibilidad con aplicaciones contables externas:** 
  * Sedipualb@ no puede imponer ni adaptar su sistema a medida para cada software contable del mercado.
  * La integración depende de que las entidades exijan dicha compatibilidad a sus proveedores de contabilidad y de que estos desarrolladores decidan integrarse con SEFACE.
  * Para facilitar este proceso, Sedipualb@ pone a disposición de cualquier aplicación contable interesada sus servicios web (*web services*) y puntos de conexión (*endpoints*) estándar.
  * Se trabaja en una integración preferente con la aplicación contable de la Diputación, la cual está siendo actualizada para permitir este flujo automatizado desde la gestión de contratos.

*Fuente: vídeo tutorial, min 92:56–98:37 — https://youtu.be/TO3KMwAOkSE?t=5576*

## Fomento del uso colaborativo y canales de soporte en SECOIN

![Captura del vídeo, capítulo 13](data/sedipualba/frames/cap13.png)

El módulo de control interno SECOIN de la plataforma Sedipualb@ busca consolidar su implantación en todo tipo de entidades locales y supramunicipales, promoviendo la colaboración activa de los usuarios para la detección de mejoras en la herramienta.

Para optimizar el uso del sistema y canalizar las aportaciones de las entidades, se establecen las siguientes pautas y recursos:

*   **Participación activa en el sistema:** Se insta a las entidades de todos los tamaños (especialmente a las grandes corporaciones y entidades supramunicipales) a integrar SECOIN en sus procesos de fiscalización y cierre de liquidaciones para aprovechar el valor del trabajo realizado.
*   **Colaboración en la mejora del producto:** El desarrollo de la herramienta se beneficia de las pruebas, sugerencias y cooperación de los usuarios y profesionales del ámbito de la intervención.
*   **Canales de soporte y consultas:** Para resolver dudas o proponer mejoras en la aplicación, los usuarios disponen de dos vías de comunicación:
    *   El Centro de Atención al Usuario (**CAO**).
    *   El correo electrónico de contacto: **administración.electronica.es** (para cuestiones pendientes o propuestas de desarrollo).
*   **Acceso a recursos formativos:** Las sesiones y grabaciones de los tutoriales se suben a la plataforma y se difunden periódicamente entre todos los usuarios de la herramienta.

*Fuente: vídeo tutorial, min 98:37–101:03 — https://youtu.be/TO3KMwAOkSE?t=5917*
