# AGENTS.md — Forma de trabajar y decisiones técnicas

Estas son preferencias explícitas del propietario del proyecto. CLAUDE.md contiene el alcance y los requisitos del reto. Lee ambos antes de trabajar. Si parece haber una contradicción, explícala y pregunta antes de tomar una decisión estructural.

## Tecnologías y sencillez

- Backend y coordinación del sistema en Go (Golang).
- Visión por computador en Python.
- Usar Playwright para automatizar el navegador. La ubicación de esa automatización y cómo se conecta con Go se acuerdan con el usuario antes de implementarlas.
- Preferir código sencillo, legible y fácil de modificar a optimizaciones complejas. Este es un prototipo de hackathon.
- No añadir servicios, base de datos, colas, frameworks, agentes autónomos, APIs de IA ni una interfaz web por iniciativa propia. Proponerlos solo si resuelven una necesidad concreta y pedir aprobación si cambian el diseño.
- Elegir la solución mínima que permita ejecutar y verificar los cuatro casos requeridos.

## Nombres

- Usar snake_case para todas las variables y parámetros propios, tanto en Go como en Python.
- Usar MAYÚSCULAS_CON_GUIONES_BAJOS para las constantes propias.
- Los nombres impuestos por bibliotecas, interfaces o herramientas conservan su forma original.
- En Go, una constante o identificador con inicial mayúscula es exportado. No cambiar la visibilidad de un símbolo para satisfacer una convención de nombres sin explicar el efecto. Para tipos y funciones exportadas, conservar las reglas necesarias del lenguaje; esta preferencia exige snake_case en variables, no en toda la API.

## Comunicación

- Hablar en español, de forma concisa y a alto nivel.
- Explicar qué se va a hacer y para qué antes de cada bloque de trabajo relevante.
- Durante el trabajo, comunicar avances, problemas y decisiones con frases breves. No narrar cada comando ni cada línea de código.
- El usuario no va a leer el código. Explicar el sistema en términos de responsabilidades: quién abre el navegador, quién interpreta imágenes, quién decide el resultado y dónde se guarda la evidencia.
- Al terminar, indicar qué funciona, cómo ejecutarlo, qué se ha comprobado y qué falta. Distinguir pruebas sintéticas de pruebas contra los juegos reales.

## Consultar decisiones importantes

Preguntar ANTES de implementar decisiones difíciles de revertir, especialmente:

- Qué componente controla Playwright y el ciclo de vida del navegador.
- Contrato de integración Go/Python y uso de subprocesos, HTTP u otra comunicación.
- Dependencias externas con coste, cuentas o claves adicionales.
- Incorporación de persistencia, servicios o cambios grandes de estructura.
- Sustitución o eliminación del código anterior, cambios de historial, despliegues o publicación externa.

Para cada decisión presentar una recomendación breve, su motivo y como máximo una alternativa útil. Esperar respuesta para el trabajo dependiente; mientras tanto se pueden analizar requisitos y preparar tareas independientes.

No pedir aprobación por detalles locales reversibles como extraer una función, corregir un fallo o escribir una prueba necesaria.

## Reinicio seguro

- Empezar desde un alcance limpio NO autoriza borrar el trabajo existente.
- Inspeccionar el estado del repositorio y los documentos anidados antes de editar. No ejecutar reset, clean ni sobrescribir archivos ajenos.
- Identificar instrucciones antiguas contradictorias y proponer su reconciliación; no mantener dos planes incompatibles en paralelo.
- No hacer commit, push o merge salvo petición del usuario.

## Primer paso

Tras leer ambos archivos y revisar el repositorio, resumir el diseño mínimo y preguntar únicamente las decisiones estructurales pendientes. No arrancar construyendo una arquitectura completa sin acordarla.
