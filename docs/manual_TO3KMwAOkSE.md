# SECOIN — complemento del webinar (lo que el manual oficial no cuenta)

Documento generado automáticamente del vídeo https://youtu.be/TO3KMwAOkSE. Los apartados ya documentados oficialmente se remiten a su manual (no se duplican); el resto se redacta desde el vídeo citando el tramo exacto.

## Introducción a SECOIN: Contexto y Funcionalidades Principales

SECOIN es la herramienta de control interno de la plataforma Sedipualb@, diseñada principalmente para facilitar las funciones de control económico-financiero encomendadas a los funcionarios de intervención en las entidades locales. Su objetivo es integrar de forma completa las funciones de control y gestión con la tramitación concreta de los expedientes administrativos.

A continuación, se detallan las características clave y el origen de la herramienta:

* **Ámbito de aplicación:** Está vinculada a la gestión de expedientes en SEGEX para garantizar la trazabilidad de las actuaciones de control interno. No obstante, puede ser utilizada por organizaciones que no gestionen sus expedientes en Sedipualb@, aunque con limitaciones en cuanto a la documentación integrada.
* **Fiscalización limitada previa:** El sistema se basa en un conjunto de formularios estandarizados (*checklists*) para la fiscalización de requisitos básicos. Estos formularios tomaron como base inicial los de la Diputación de Girona, adaptados por un grupo de trabajo de interventoras de la administración local de entidades usuarias de la plataforma.
* **Gestión de reparos:** Permite el control de los reparos formulados y de su resolución, integrando este proceso para su posterior remisión al Tribunal de Cuentas.
* **Fiscalización plena:** Además de la fiscalización limitada, la herramienta habilita la posibilidad de emitir informes de fiscalización plena bajo las mismas características metodológicas.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap01.png)

*Fuente: vídeo, min 0:00–4:02 — https://youtu.be/TO3KMwAOkSE?t=0*

## Módulo SECOIN: Control Interno y Tipos de Informes

El módulo SECOIN de Sedipualb@ facilita la gestión y emisión de los diferentes informes exigidos en el ámbito del control interno municipal, estructurando el flujo de trabajo en tres áreas clave de fiscalización.

*   **Fiscalización Limitada Previa de Requisitos Básicos:**
    *   Permite la emisión de informes en las distintas fases de la gestión del gasto.
    *   La mayor parte de la actividad se concentra en la **fase O** (reconocimiento de la obligación), seguida de la **fase AD** (autorización y disposición) y la **fase A** (autorización).
    *   Es una herramienta consolidada y automatizada a través de formularios normalizados.

*   **Informes de Control Financiero No Planificable:**
    *   Herramienta diseñada para la emisión de informes de control financiero que no están sujetos a la planificación anual.
    *   Su desarrollo se basa en los modelos y formularios de la Diputación de Girona y en la experiencia de uso del Ayuntamiento de Palma de Mallorca.

*   **Informes de Omisión de la Fiscalización:**
    *   Mecanismo incorporado para completar el ciclo de control interno.
    *   A diferencia de los anteriores, estos informes no siguen un patrón rígido y están sujetos a criterios interpretativos, ofreciendo una solución práctica para documentar las omisiones detectadas.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap02.png)

*Fuente: vídeo, min 4:02–8:34 — https://youtu.be/TO3KMwAOkSE?t=242*

## Puesta en marcha y configuración inicial de SECOIN

El módulo SECOIN (Control Interno Municipal) de la plataforma Sedipualb@ permite gestionar la fiscalización, el control permanente y la gestión de reparos de las entidades locales. Para comenzar a utilizar la aplicación y realizar su configuración inicial, se deben seguir los pasos y directrices detallados a continuación:

### 1. Alta de la entidad en el sistema
* **Acceso inicial:** Para acceder, introduzca en el navegador la dirección web correspondiente a su entidad seguida de `/secoin` (ej. `[url_entidad]/secoin`).
* **Solicitud de alta:** Si la entidad aún no está registrada, el sistema mostrará el mensaje *"Esta entidad no está de alta"*. En este caso, debe abrir un **ticket de soporte** para solicitar el alta.
* **Carga de plantillas:** Tras el alta, el equipo de soporte facilitará precargadas las plantillas y formularios necesarios para el funcionamiento de la aplicación (utilizando modelos de ejemplo o plantillas cedidas por otras entidades usuarias).

### 2. Estructura de la aplicación
La herramienta se divide en las siguientes secciones principales:
* **Áreas y Formularios:** Espacio donde se gestionan las plantillas de la aplicación. Las áreas de fiscalización contienen expedientes y, dentro de estos, se encuentran los formularios (actuaciones que sirven de plantilla para fiscalizar).
* **Fiscalizaciones:** Sección para la realización de fiscalizaciones, gestión de reparos, control permanente (control financiero) y omisiones (esta última en fase de pruebas).
* **Configuración y Utilidades:** Permite la exportación de datos y la parametrización del sistema.

### 3. Gestión de plantillas y requisitos
Las plantillas de fiscalización vienen precargadas, pero pueden editarse y adaptarse a las necesidades de cada entidad:
* **Tipos de requisitos:** Se componen de requisitos básicos, adicionales y otros requisitos de verificación.
* **Configuración de requisitos:** Al editar o crear un requisito, se debe introducir el enunciado, la referencia legal y determinar si se activa la casilla **"Permite no procede"**.
* **Cumplimentación:** Durante la fiscalización, cada requisito se debe marcar como **Sí**, **No** o, si está habilitado, como **No procede** (lo que excluye ese requisito del cálculo de la fiscalización actual).

### 4. Configuración de numeración y cambio de ejercicio
Al iniciar el año o al acceder por primera vez, puede aparecer un mensaje de advertencia indicando que la fecha de trabajo no coincide con la fecha actual. Esto se debe a que la numeración de los informes debe actualizarse para el nuevo ejercicio:
* **Acceso a la configuración:** Diríjase a la ventana de configuración de la aplicación, la cual permite parametrizar las fiscalizaciones limitadas, las fiscalizaciones plenas, los reparos y el control permanente.
* **Edición del formato:** Al editar la configuración de un tipo de informe, puede definir:
  * El **prefijo** (por ejemplo, el año actual y las siglas del tipo de informe, como `2024_FLZ`).
  * El **número de dígitos** del contador (por ejemplo, 4 dígitos).
  * El **sufijo** o texto posterior al número.
  * El **número inicial** del contador (se establece en `0` al iniciar el año, o en el número correlativo deseado si se prefiere continuar la numeración de una herramienta externa anterior).

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap03.png)

*Fuente: vídeo, min 8:34–16:02 — https://youtu.be/TO3KMwAOkSE?t=514*

## Configuración de Informes y Firmas en SECOIN

Este apartado describe las opciones de configuración para la generación, firma y validación de informes de control interno en el módulo SECOIN, así como los roles que intervienen en el proceso.

### Opciones de Configuración de Informes
*   **Idioma de los informes:** Permite configurar el idioma de salida de los documentos (disponible en español y catalán).
*   **Enviar a firmar automáticamente:** 
    *   **Desmarcado:** El sistema genera un documento en SEFYCU que queda en estado de borrador (pendiente de enviar a firmar).
    *   **Marcado (Recomendado):** El documento se crea en SEFYCU directamente listo para la firma.
*   **Firma automatizada mediante sellado de órgano:** Permite agilizar el proceso firmando el informe a través de un sello de órgano, siempre que se defina y regule como una actuación administrativa automatizada (conforme al artículo 41 de la Ley 40/2015). Al optar por esta vía, el informe se incorpora directamente al expediente, el cual cambia de estado y muestra el resultado de la última fiscalización realizada.

### Roles en el Proceso de Fiscalización
El acceso y la elaboración de los informes se estructuran bajo dos roles diferenciados:
1.  **Fiscalizador:** Realiza la primera revisión del formulario. Cualquier acceso requiere la identificación con su certificado de firma electrónica. En el informe final queda constancia de su identidad como redactor.
2.  **Interventor (Interventor/a o Viceinterventor/a):** Revisa el informe preparado por el fiscalizador y puede aceptarlo, modificarlo o rechazarlo para que se realice una nueva fiscalización. Es quien firma el documento que se incorpora al expediente.

### Validación de Plantillas y Requisitos Legales
*   **Fecha de acuerdo de pleno:** Es un dato obligatorio para la puesta en marcha de la fiscalización limitada previa (exigido por el Real Decreto de control interno). Esta fecha debe indicarse en la configuración para que se muestre correctamente en los informes generados.
*   **Fecha de último pleno (Recomendable):** Permite predefinir una fecha de validación para las plantillas. Al validar múltiples plantillas (cuyo contenido puede variar con el tiempo al añadir requisitos o comprobaciones), el sistema propondrá automáticamente esta fecha, evitando tener que introducirla manualmente en cada una de ellas.
*   **Control financiero permanente:** A diferencia de la fiscalización limitada, los formularios de control permanente no planificable están precargados y no requieren legalmente la indicación de un acuerdo de pleno para su puesta en marcha, aunque los informes son preparados por el órgano interventor.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap04.png)

*Fuente: vídeo, min 16:02–21:46 — https://youtu.be/TO3KMwAOkSE?t=962*

## Configuración inicial y gestión de formularios en SECOIN

Para poner en marcha el módulo de control interno, la entidad debe gestionar y validar los formularios que utilizará en sus procesos de fiscalización y control financiero. A continuación, se detallan los aspectos clave para su configuración y funcionamiento:

*   **Selección y aprobación de formularios:** 
    *   La aplicación dispone de un catálogo de aproximadamente 220 formularios distribuidos por áreas.
    *   Se recomienda que cada entidad apruebe y valide únicamente los formularios que vaya a utilizar (por ejemplo, entre 10 y 30), activando nuevos formularios solo a medida que surja la necesidad.
*   **Ubicación de los formularios según el tipo de control:**
    *   **Fiscalización limitada:** Los formularios correspondientes se gestionan desde el área general de formularios de la entidad.
    *   **Control financiero:** Se ubican dentro del área denominada por defecto *Control permanente no planificable* (cuyo nombre es personalizable por la entidad).
*   **Integración con SEGRA y puesta en marcha:**
    *   El proceso inicial requiere revisar los formularios para aceptarlos, modificarlos o sustituirlos.
    *   En el caso específico de la Fiscalización Limitada, es necesario adoptar el acuerdo correspondiente en el Pleno municipal e incorporar dicho acuerdo al sistema.
*   **Cumplimentación y firma:**
    *   Una vez seleccionado el formulario, se procede a su firma.
    *   La firma puede realizarse mediante la firma electrónica personalizada del interventor o a través de un sistema de firma de órgano, diseñado para agilizar el proceso cuando existe un volumen elevado de documentos.
*   **Explotación de datos:**
    *   Toda la información cumplimentada se almacena en estructuras de datos estructuradas. El resultado de cada formulario queda registrado y disponible para su posterior explotación y generación de informes.
*   **Soporte técnico:**
    *   Para la resolución de dudas durante la puesta en marcha, se puede consultar la videoteca de ayuda del sistema o solicitar asistencia técnica a través del Centro de Atención al Usuario (CAO).

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap05.png)

*Fuente: vídeo, min 21:46–25:17 — https://youtu.be/TO3KMwAOkSE?t=1306*

## Registro y Tramitación de Omisiones de la Función Interventora en SECOIN

El módulo SECOIN de Sedipualb@ permite registrar, gestionar y tramitar los informes de omisión de la función interventora. El procedimiento está diseñado para facilitar la elaboración del informe, asegurar que se recojan todas las actuaciones de control interno y simplificar el envío de los datos requeridos por el Tribunal de Cuentas (conforme al artículo 28.1 del Real Decreto 424/2017).

### 1. Inicio del procedimiento: Diligencia de apertura
Cuando el órgano interventor detecta una posible omisión en un expediente, el flujo de trabajo se inicia con una **diligencia de apertura**. Esta diligencia comunica la incidencia al centro gestor y le requiere una memoria explicativa.

Para dar de alta una nueva omisión en el sistema, se deben cumplimentar los siguientes campos:

*   **Expediente origen:** Introducir el número de expediente de SEGEX donde se ha detectado la omisión para vincular ambos expedientes.
*   **Centro / Área gestora:** Identificar el departamento responsable del expediente originario.
*   **Expediente de resolución:** Abrir el expediente administrativo específico donde se resolverá la omisión de la función interventora.

### 2. Datos de la omisión (Art. 28.1 RD 424/2017 y metadatos)
A continuación, se deben rellenar los datos que identifican y clasifican la omisión, los cuales coinciden con la información exigida por el Tribunal de Cuentas:

*   **Datos del tercero:** NIF y nombre o razón social del tercero afectado.
*   **Categoría de la omisión:** Seleccionar si se produjo en una fiscalización previa (limitada o plena) o en una comprobación material de la inversión.
*   **Importe:** Cuantía económica estimada de la fase del gasto afectada.
*   **Clasificación del gasto:** 
    *   Aplicación presupuestaria.
    *   Modalidad y naturaleza del gasto.
    *   Tipo de expediente (por ejemplo: contratación, gasto en concesión de obras, etc.).
    *   Objeto del gasto.
*   **Observaciones:** Campo libre para añadir cualquier dato complementario.

### 3. Requerimiento de información al Centro Gestor
La herramienta genera una plantilla de requerimiento basada en las instrucciones de control interno, donde se solicita al centro gestor que aporte:
*   Acreditación de que las prestaciones realmente se han ejecutado.
*   Justificación de los motivos por los que no se sometió el expediente a fiscalización previa.
*   Declaración expresa sobre si se puede producir la devolución o restitución del bien, o si existen gastos susceptibles de indemnización.

*Nota de flexibilidad:* El sistema incluye un campo de **"Cuerpo de informe adicional"**. Este espacio en blanco permite al interventor añadir requerimientos específicos o información personalizada que no figure en la plantilla por defecto (útil, por ejemplo, en omisiones de comprobación material de la inversión).

### 4. Generación del documento
Una vez completados los campos anteriores, se debe pulsar el botón **"Generar"**. El sistema procesará la información y mostrará una previsualización de la **diligencia de apertura** (no del informe final) con todos los antecedentes y datos estructurados para su firma y envío al centro gestor.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap06.png)

*Fuente: vídeo, min 25:17–41:12 — https://youtu.be/TO3KMwAOkSE?t=1517*

## Cumplimentación del Informe de Omisión de la Función Interventora (Artículo 28)

Este apartado describe cómo cumplimentar los campos del informe de omisión de la función interventora en el módulo SECOIN, cuya parametrización está alineada con el artículo 28 del Reglamento de Control Interno y los metadatos requeridos para la remisión de información al Tribunal de Cuentas.

*   **Supuesto de nulidad (Artículo 47 de la Ley 39/2015):** 
    *   Se debe responder obligatoriamente con **Sí** o **No**.
    *   Si se responde **Sí**, el sistema obliga a seleccionar uno o varios motivos de nulidad de la lista desplegable (prescindencia total del procedimiento, falta de consignación presupuestaria, tramitación de contrato menor improcedente, u otros).
*   **Constatación de las prestaciones realizadas (Apartado C del Artículo 28):** Campo de texto libre para informar sobre la conformidad de la factura o las valoraciones del interventor basadas en la memoria explicativa del centro gestor y el expediente.
*   **Constatación de la existencia de crédito:** Verificación de la disponibilidad de crédito en la aplicación presupuestaria indicada en la diligencia de apertura.
*   **Propuesta de revisión de oficio:** 
    *   Si previamente se marcó que **Sí** existe un supuesto de nulidad, el sistema habilitará la opción que constata la existencia de incumplimientos normativos que pueden calificar el acto como nulo.
    *   Se incluye un campo de texto libre para la conclusión final del interventor (procedencia de la revisión, pago de indemnización u otra consideración).
    *   Al final del formulario, se debe registrar como metadato estructurado si la conclusión final propone la revisión de oficio o el pago de las facturas por economía procesal (esta opción solo se habilita si se confirmó el supuesto de nulidad).
*   **Órgano competente para adoptar el acuerdo:** Selección del órgano que debe aprobar el acuerdo de continuidad (habitualmente el Presidente/Alcalde, o el Pleno si este fuera el competente para el gasto objeto de omisión).
*   **Reconocimiento Extrajudicial de Créditos (REC):** Indicación de si el expediente, tras resolver la omisión, requiere aprobación mediante REC para su imputación al presupuesto.
*   **Exigencia de responsabilidades:** Declaración de si la infracción puede derivar en la exigencia de responsabilidades penales o contables.
*   **Ejercicio de generación del gasto:** Indicación de si el gasto omitido corresponde al ejercicio corriente o a ejercicios anteriores.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap07.png)

*Fuente: vídeo, min 41:12–47:22 — https://youtu.be/TO3KMwAOkSE?t=2472*

## Generación y estructura del informe de omisión de la función interventora

El módulo SECOIN de Sedipualb@ facilita la elaboración del informe de omisión de la función interventora, permitiendo la incorporación de metadatos para su explotación y la remisión automatizada de información al Tribunal de Cuentas.

### Pasos para la incorporación de documentos y generación del informe

1. **Selección de documentos del expediente:** Al realizar la búsqueda desde el informe de omisión, el sistema accede directamente a los documentos del expediente en tramitación (como la memoria aportada por el centro gestor). Seleccione el documento correspondiente, súbalo y guarde los cambios para actualizar los datos.
2. **Cumplimentación de campos y metadatos:** Complete la información requerida a lo largo de las diferentes secciones del informe. Estos datos estructurados actuarán como metadatos en el sistema.
3. **Confirmación del borrador:** Una vez cumplimentados los campos, confirme el borrador para generar el documento definitivo dentro del expediente.

### Estructura y contenido del informe

El documento generado se estructura bajo los requisitos normativos y contiene los siguientes apartados:

* **Descripción del gasto:** Incluye los datos del primer apartado del artículo 28 de la normativa aplicable.
* **Fundamentos jurídicos:** Apartado basado en una plantilla predefinida.
* **Exposición de incumplimientos normativos:** Correspondiente al segundo apartado del artículo 28, donde se detalla la explicación de los incumplimientos y se incorpora la categorización de los mismos establecida por el Tribunal de Cuentas.
* **Prestaciones realizadas:** Cuerpo del informe correspondiente al apartado C.
* **Constatación de la existencia de crédito:** Contenido correspondiente al apartado D.
* **Revisión de oficio:** Apartado E, donde se informa sobre la procedencia o no procedencia de dicha revisión.
* **Conclusión final:** Dispone de un campo de texto libre para que el interventor añada las consideraciones necesarias, junto con un texto fijo normativo que advierte que la omisión de la función interventora puede dar lugar a conductas culpables, infracciones administrativas y a la exigencia de las responsabilidades correspondientes.

### Utilidad de la metadatación y explotación de datos

La introducción de estos datos estructurados en SECOIN permite:

* **Automatización:** Facilita la remisión automatizada de la información al Tribunal de Cuentas.
* **Explotación de información:** Permite analizar y detectar patrones estadísticos en los expedientes, tales como:
  * Si las omisiones se deben a supuestos de nulidad (por falta de procedimiento) o de anulabilidad.
  * El porcentaje de informes en los que se propone la revisión de oficio.
  * El volumen de casos en los que se ha requerido un reconocimiento extrajudicial de créditos.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap08.png)

*Fuente: vídeo, min 47:22–51:27 — https://youtu.be/TO3KMwAOkSE?t=2842*

## Gestión de Informes de Omisión de la Función Interventora en SECOIN

El módulo SECOIN de Sedipualb@ permite la generación y parametrización de los informes de omisión de la función interventora, así como de los metadatos requeridos para su remisión al Tribunal de Cuentas.

### Criterios para la generación y agrupación de informes

* **Regla general de individualización:** El Tribunal de Cuentas exige información detallada e individualizada. Como norma general, se recomienda realizar **un informe por cada omisión** detectada.
* **Criterios de agrupación excepcional:** Solo se aconseja agrupar varias facturas en un único informe cuando exista una estricta **identidad de causa, motivo, proveedor (tercero) y aplicación presupuestaria**. 
  * Si las facturas corresponden a diferentes terceros, el sistema no permitirá la agrupación.
  * No se deben unificar omisiones de distinta naturaleza en un solo informe, ya que esto impediría la correcta explotación de los datos (por ejemplo, identificar en qué capítulo o programa presupuestario se produjo la omisión).

### Puesta en marcha y disponibilidad del sistema

* **Acceso global sin configuración previa:** A diferencia de otras utilidades, la función de omisiones no requiere la creación de plantillas ni parametrizaciones iniciales por parte del usuario. Estará disponible de forma automática para todas las entidades.
* **Entorno de pruebas:** La funcionalidad ya se encuentra habilitada en la plataforma de pruebas para que los usuarios puedan testear su funcionamiento y resolver posibles dudas.
* **Paso a producción:** La activación definitiva en el entorno de producción está planificada para el **1 de abril**.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap09.png)

*Fuente: vídeo, min 51:28–55:53 — https://youtu.be/TO3KMwAOkSE?t=3088*

## Control Financiero Permanente No Planificable en SECOIN

Este módulo de la plataforma Sedipualb@ permite a los interventores gestionar el control financiero permanente no planificable de forma flexible y progresiva, facilitando la homogeneización de criterios y la explotación de datos para el informe resumen anual.

### Características principales e implantación

* **Implantación inmediata y autónoma:** No requiere de un acuerdo formal de la corporación ni de una configuración compleja de requisitos mínimos. Puede ponerse en marcha de un día para otro.
* **Activación progresiva:** No es necesario activar todas las fichas de control a la vez. Se recomienda iniciar el trabajo con una sola ficha (por ejemplo, una modificación de crédito) e ir activando el resto de forma paulatina conforme se vayan necesitando.
* **Fichas precargadas:** El sistema parte de una precarga de fichas basadas en las guías de la Diputación de Girona, las cuales sirven como guía de comprobación.
* **Funcionamiento semiautomático:** A diferencia de la fiscalización limitada (basada en respuestas de "sí" o "no"), en esta modalidad el resultado del informe se construye de manera más manual por parte del interventor.
* **Uso de anexos de cálculo:** Debido a la naturaleza de este control, la mayoría de las fichas (como las de estabilidad, presupuesto o liquidación) se complementan anexando los documentos de cálculo propios que elabora la intervención.

### Instrucciones de acceso y creación de un nuevo control

A diferencia de la fiscalización limitada, que requiere acceder primero a un formulario específico, el inicio en este módulo es más directo:

1. Acceda a la pestaña de **Control Financiero** dentro de la plataforma.
2. Haga clic en el botón **Nuevo**.
3. Seleccione la ficha de control deseada directamente desde la lista completa de fichas disponibles que se desplegará en pantalla.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap10.png)

*Fuente: vídeo, min 55:53–70:19 — https://youtu.be/TO3KMwAOkSE?t=3353*

## Gestión de Datos y Documentación Anexa en Informes de Control Interno (SECOIN)

El módulo SECOIN de Sedipualb@ permite optimizar el registro de datos y la emisión de informes de control interno, garantizando la trazabilidad de los expedientes sin necesidad de duplicar información ya existente en la plataforma.

### Registro simplificado de modificaciones de crédito
Para optimizar el trabajo y evitar la carga manual innecesaria de datos en expedientes con múltiples partidas (como las transferencias de crédito), se recomienda seguir el siguiente criterio práctico:
* **Registrar solo datos esenciales:** No es necesario cumplimentar individualmente cada una de las partidas presupuestarias afectadas.
* **Consolidar importes:** Introducir únicamente el importe totalizado del aumento y de la minoración de la transferencia. Este dato actúa como el metadato clave para la exportación y la obtención de una visión global del volumen de la corporación.
* **Vincular mediante CSV:** La propuesta detallada y sus partidas ya constan en el expediente electrónico. Para evitar duplicidades, el informe de control permanente se enlaza directamente al Código Seguro de Verificación (CSV) de dicha propuesta.

### Alternativas para la incorporación de documentos anexos
Actualmente, la herramienta no dispone de una función nativa para adjuntar anexos directamente dentro del formulario del informe. Para aquellos informes que requieran obligatoriamente cálculos o documentación complementaria (como informes de estabilidad de la liquidación, presupuestos, endeudamiento o competencias impropias), se pueden utilizar dos alternativas:

1. **Referencia cruzada por CSV:** Redactar el informe en la herramienta y hacer mención expresa en el texto al CSV del documento de cálculos (previamente firmado y subido a la plataforma), garantizando así la relación indisoluble entre ambos.
2. **Generación de un documento único (Fusión PDF):** 
   * Descargar el informe generado por la herramienta.
   * Unificar el informe y los PDFs de los cálculos o anexos en un solo documento.
   * Firmar el documento resultante de forma conjunta a través de un expediente de firma (SEFYCU) para remitirlo como un único archivo indisoluble al órgano de tutela correspondiente.

### Trazabilidad y rigor del expediente electrónico
En la mayoría de los expedientes de control (como las modificaciones de crédito ordinarias), no es imprescindible anexar físicamente los documentos al informe. La plataforma **SEGEX** garantiza la trazabilidad absoluta mediante:
* Una **bitácora de registro** que graba el autor, fecha, hora, minuto y segundo de incorporación de cada documento.
* La constatación de que el informe se emite en una fecha concreta sobre el estado y los documentos exactos que existían en el expediente electrónico en ese momento.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap11.png)

*Fuente: vídeo, min 70:19–83:51 — https://youtu.be/TO3KMwAOkSE?t=4219*

## Integración de SECOIN con SEGRA y Gestión de Rectificaciones en Fiscalizaciones

Este apartado describe las mejoras introducidas en el módulo SECOIN para optimizar la fiscalización de propuestas de resolución unipersonales gestionadas en SEGRA, así como la nueva funcionalidad para la cancelación de fiscalizaciones erróneas.

### Fiscalización de Propuestas de Resolución en SEGRA

La fiscalización es una actuación previa a la adopción de decisiones que se realiza sobre propuestas de acuerdo o de resolución. En el caso de resoluciones de órganos unipersonales tramitadas a través de la herramienta SEGRA, se ha agilizado el proceso de firma del informe de fiscalización (favorable o desfavorable) directamente desde el flujo de trabajo:

* **Identificación del tipo de documento:** Al seleccionar un elemento para fiscalizar en el sistema, este identifica automáticamente el origen del documento:
  * Si es un documento de **SEFYCU**, se muestra el CSV con un enlace directo al documento correspondiente.
  * Si es una propuesta de **SEGRA** anexada al expediente, el sistema lo indica explícitamente.
* **Acceso directo para la firma:** Para las propuestas de SEGRA, se ha incorporado un enlace directo que redirige al usuario al expediente de SEGRA. Esto permite registrar la firma (favorable o desfavorable) con un solo clic, reduciendo los pasos manuales requeridos en la herramienta.

### Rectificación y Cancelación de Fiscalizaciones

En el ámbito de las fiscalizaciones limitadas, el sistema ofrece alternativas para subsanar errores en registros ya realizados:

* **Rectificar una fiscalización:** Al utilizar esta opción, el sistema genera una nueva ficha de fiscalización basada en el mismo formulario que la anterior para poder corregir los datos necesarios.
* **Cancelar una fiscalización:** Si no se desea reutilizar la ficha existente y se requiere anular el proceso, se ha habilitado el botón **"Cancelar"** (o "Cancelado"). Al pulsarlo, el sistema muestra las instrucciones en pantalla para completar el proceso, las cuales requieren que el usuario acceda al expediente y cancele manualmente el documento SEFYCU o el informe que se había generado originalmente.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap12.png)

*Fuente: vídeo, min 83:51–91:39 — https://youtu.be/TO3KMwAOkSE?t=5031*

## Explotación de datos, informes y conectividad contable en SECOIN

El módulo SECOIN de la plataforma Sedipualb@ permite la gestión de datos de control interno municipal, facilitando la extracción de información y la tramitación administrativa integrada. A continuación, se detallan las funcionalidades clave de explotación de datos y el estado de la integración con los sistemas de contabilidad:

*   **Extracción de datos y elaboración de informes:**
    *   Los datos contenidos en el sistema son explotables mediante la exportación de ficheros en formatos **CSV o Excel** desde los menús correspondientes de la aplicación.
    *   Se trabaja en el desarrollo a medio plazo de un **borrador de informe automático**. Este borrador integrará directamente elementos extraídos del sistema, tales como el número de fiscalizaciones realizadas, sus resultados, omisiones, reparos e informes de control financiero no planificable.

*   **Relación actual entre fiscalización y contabilidad:**
    *   Al elaborar un informe de fiscalización, el usuario puede incorporar manualmente la partida presupuestaria y el importe. 
    *   Actualmente, **este dato no se obtiene de la contabilidad ni se envía a ella de forma automática**; es un dato de registro interno dentro del proceso de fiscalización.

*   **Proyecto de integración contable y gestión de contratos:**
    *   El objetivo de la plataforma es conectar la gestión del gasto, la contratación y la tramitación de facturas con la contabilidad.
    *   Se está desarrollando la posibilidad de **disparar la contabilización automáticamente** desde la gestión administrativa de los contratos (a través de la plataforma de tramitación SECA), donde se dictan los actos administrativos y sus diferentes fases.
    *   La plataforma Sedipualb@ centraliza la información de las facturas (estado de pago, ubicación y autorizaciones) para las entidades que utilizan SECA y SEFACE integrado.

*   **Compatibilidad con aplicaciones contables externas:**
    *   La integración definitiva depende de que las empresas desarrolladoras de los programas de contabilidad de cada entidad decidan integrarse con SEFACE.
    *   Sedipualb@ no realiza desarrollos a medida para cada software contable privado, sino que ofrece **servicios web (web services) y puntos de conexión (endpoints)** abiertos para que cualquier aplicación contable externa pueda integrarse con la plataforma.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap13.png)

*Fuente: vídeo, min 91:39–98:37 — https://youtu.be/TO3KMwAOkSE?t=5499*

## Fomento del uso colaborativo y canales de soporte de SECOIN

El módulo de control interno (SECOIN) de Sedipualb@ se encuentra en una fase de expansión, con cerca de 60 entidades activas. Para optimizar la herramienta y aprovechar el valor del trabajo realizado, se promueve la incorporación activa de todo tipo de entidades (municipales, grandes ayuntamientos y supramunicipales) en tareas como la fiscalización y el cierre de liquidaciones.

Para colaborar en la mejora del sistema y resolver dudas, se dispone de los siguientes recursos y canales:

*   **Soporte técnico y consultas:** Apertura de incidencias o dudas a través del Centro de Atención al Usuario (CAO).
*   **Propuestas de mejora:** Envío de sugerencias y consultas adicionales al correo electrónico `administracion.electronica.es` (o el canal equivalente de la plataforma).
*   **Material de consulta:** Acceso a las grabaciones de las sesiones formativas y tutoriales, las cuales se difunden periódicamente a todos los usuarios de la herramienta.
*   **Desarrollo del producto:** El diseño y desarrollo de la herramienta es una iniciativa liderada por la Diputación de Albacete, basada en la cooperación y el testeo de propuestas por parte de los interventores y técnicos colaboradores.

![captura](data/sedipualba/frames/TO3KMwAOkSE/cap14.png)

*Fuente: vídeo, min 98:37–101:03 — https://youtu.be/TO3KMwAOkSE?t=5917*
