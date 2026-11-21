# Rediseño del README de perfil de GitHub como pila de tarjetas SVG animadas

## Specs

S1. La página del perfil renderiza una pila de tarjetas SVG animadas: `cards/header.svg` (nombre, una línea sobre mí, retrato opcional), tres mosaicos vinculados en una fila (cada uno una etiqueta `<img>` con ancho 32,5%), `cards/contributions-monthly.svg` (contribuciones por mes + racha, días activos y día de mayor actividad), una tarjeta por repositorio destacado (`cards/repo-<name>.svg`), y `cards/contributions-graph.svg` (gráfico de contribuciones anual con el color de marca).

S2. Las tarjetas se muestran mediante etiquetas `<img>`, así que cada SVG usa únicamente técnicas que funcionan en ese contexto: bloque `<style>` en línea con fotogramas clave CSS, elementos SMIL `<animate>`, y fuentes subconjunto generadas con pyftsubset e incrustadas como URI de datos WOFF base64. Sin JavaScript y sin referencias a recursos externos.

S3. Colores y fuentes adaptados del sitio web (portafolio-psi-five-95.vercel.app): paper `#0a0e17`, tarjeta `#121826`, tinta `#e8eef7`, tinta tenue `#94a3b8`, línea `#1e293b`, acento `#22d3ee`, acento suave `#083344`; tipografías Outfit (títulos) y Source Sans 3 (cuerpo).

S4. Los retrasos de animación están escalonados para que la página se reproduzca de arriba a abajo; todas las animaciones se desactivan bajo `prefers-reduced-motion`.

S5. Los datos de contribución se leen de `data/contributions.json`, que una acción programada de GitHub actualiza diariamente; la misma acción agrega un paso que ejecuta el script de render y confirma las tarjetas.

S6. El script soporta `STATIC=1`, que renderiza el fotograma final (todas las animaciones en su estado final) para capturar la imagen antes de enviar.

## Tasks

T1 S3 — Descargar fuentes (Outfit, Source Sans 3) y pipeline pyftsubset → WOFF → base64. commit
T2 S5 — `scripts/fetch_contributions.py` (GitHub GraphQL) + `data/contributions.json` de ejemplo; estadísticas (racha, días activos, día más activo) con tests. commit
T3 S2,S3,S4,S6 — Núcleo de `scripts/render_cards.py`: tema, fuentes embebidas, escalonado, STATIC=1, reduced-motion. commit
T4 S1 — Render de tarjetas: header, 3 mosaicos, gráfico mensual, tarjetas de repos, gráfico de contribuciones. commit
T5 S1 — `README.md` con etiquetas img y anchos 32,5%. commit
T6 S5 — Workflow `.github/workflows/update.yml` programado. commit

## Log

L1 (verbatim): "Rediseña el archivo README de mi perfil de GitHub (https://github.com/eduardomendozavillar) como una pila de tarjetas SVG animadas. Lee primero mi archivo README actual y mi sitio web, y adapta sus colores y fuentes. Escribe un script de Python que renderice cada tarjeta en cards/: un encabezado con mi nombre, una línea sobre mí y un retrato opcional; tres mosaicos vinculados en una fila (cada uno una imagen con un ancho del 32,5%); un gráfico de mis contribuciones por mes con mi racha, días activos y día de mayor actividad; una tarjeta por repositorio destacado; y mi gráfico de contribuciones con el color de mi marca. Las tarjetas se muestran a través de etiquetas img, así que usa solo lo que funciona allí: un bloque de estilo en línea con fotogramas clave CSS, elementos SMIL animate y fuentes subconjunto con pyftsubset e incrustadas como URI de datos WOFF base64. Escalona los retrasos para que la página se reproduzca de arriba a abajo y desactiva todas las animaciones en prefers-reduced-motion. Lee los datos de contribución de un archivo JSON que una acción programada de GitHub actualiza diariamente y agrega un paso a esa acción que ejecuta el script y confirma las tarjetas. Agrega un modo STATIC=1 que muestra el fotograma final para que pueda capturarlo antes de enviarlo."

L2: El perfil aún no tiene el repositorio `eduardomendozavillar/eduardomendozavillar` (404 en la API); el README actual no existe. Se construye la estructura completa para ese repositorio nuevo.

L3: Decisión técnica: los repos destacados se toman del sitio web (Portafolio, taller.by, SGDI). taller.by no tiene repo público aún, así que la tarjeta queda controlada por `data/profile.json` (lista editable de repos, con enlace demo/código).

L4 (evidencia): 17/17 tests en verde; 9 tarjetas bien formadas (87–105 KB); verificado visualmente con Chrome headless: modo STATIC = fotograma final completo, modo animado converge al mismo fotograma; fuentes Outfit/Source Sans 3 a ~21 KB WOFF c/u; SMIL (shine gradientTransform, count-up con <set>) se desactiva en STATIC y bajo prefers-reduced-motion vía CSS. Commits: a00a5a6 (fuentes), 5582655 (fetch+stats), c266abf (renderer), 7252867 (README+workflow).

L5: Publicar el repo como `eduardomendozavillar/eduardomendozavillar` (rama main) queda para el usuario: push, creación del repo y verificación del cron de la Action son decisiones de entrega.
