---
phase: quick-260716-tkj
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .claude/CLAUDE.md
autonomous: true
requirements: [DOC-CLAUDEMD-V03]

must_haves:
  truths:
    - CLAUDE.md ya no afirma que el shell de escritorio sea Tauri; dice Electron (electron-vite)
    - El core value inyectado en cada sesión es el de 0.3 (el manga se lee dentro de la app), no el de migración de 0.2
    - Ningún agente lee ya que construir features de manga viole el scope — el bullet **Scope** caducado no existe
    - El bullet **Versionado** (semver estricto, 0.2.x fixes / 0.3.0+ features) ocupa su sitio
    - Los otros seis bloques marcados del fichero quedan BYTE-idénticos
    - Los dos marcadores del bloque siguen presentes, exactamente una vez cada uno
  artifacts:
    - .claude/CLAUDE.md (bloque GSD:project-start alineado con PROJECT.md)
  key_links:
    - "PROJECT.md es la fuente de verdad: el texto se COPIA, no se reinventa"
    - "Los marcadores GSD:project-start / GSD:project-end delimitan el bloque: si cambian, el bloque deja de ser reemplazable y el resto del fichero deja de estar protegido"
---

<objective>
`.claude/CLAUDE.md` se inyecta en TODAS las sesiones de Claude de este repo. Su bloque
`GSD:project-start` quedó congelado en 0.2 y hoy inyecta tres afirmaciones falsas:

1. Dice que el shell es Tauri 2 + Rust. La 0.2 (Tauri → Electron) se envió el 2026-07-13.
2. Su core value es el de la migración («el tracking funciona idéntico tras cambiar el motor»).
   PROJECT.md dice explícitamente que ese core value «se cumplió y caducó».
3. Su bullet **Scope** dice que la 0.2 es engine-swap puro y que nada de features nuevas. El
   milestone activo es **v0.3 «Nyanko lee manga»**. Este es el daño real: le dice a cada agente
   que construir el reader viola el scope. Ya obligó a un revisor a razonar a la contra durante la
   planificación de la Fase 4.

Propósito: dejar de mentirle al contexto de cada sesión.
Output: un bloque de ~33 líneas alineado con PROJECT.md. Nada más del fichero se toca.
</objective>

<context>
@.planning/PROJECT.md
@.claude/CLAUDE.md
</context>

<analysis>
## Es una sustitución de bloque, no una edición línea a línea

El bloque es el fichero entero desde la línea 1 hasta la 33 (`<!-- GSD:project-end -->`). Sustituirlo
de golpe por el texto de `<target_block>` es más corto Y más seguro que cinco ediciones puntuales: no
hay forma de dejarse media frase vieja dentro.

## `gsd-tools generate-claude-md` está PROHIBIDO en esta tarea

Es la vía «oficial» y arregla el bloque Project correctamente — pero regenera TODAS las secciones y
re-apunta el bloque Stack a `.planning/research/STACK.md`, un artefacto de research de 363 líneas.
Eso lleva CLAUDE.md de 84 a 284 líneas, inyectadas en cada sesión para siempre. Verificado
empíricamente: el comando **ignora `--dry-run` y escribe de verdad**. La escritura se hizo y se
revirtió; el árbol está limpio. **No lo ejecutes.** El usuario eligió la edición a mano tras ver las
cuatro opciones; no se re-abre el debate.

## El tradeoff está conocido y aceptado

Una edición a mano vive dentro de un bloque generado por marcadores, así que un futuro
`generate-claude-md` la pisaría. El usuario lo acepta: nada ejecuta ese comando automáticamente. **No
añadas maquinaria para defenderte de eso, ni un comentario de aviso dentro del bloque.**

## De dónde sale cada línea del texto nuevo

Todo se copia de PROJECT.md, no se inventa:

| Parte del bloque | Fuente |
|---|---|
| Párrafo descriptivo | PROJECT.md «What This Is» (líneas 5-10) |
| Core Value | PROJECT.md «Core Value» (líneas 22-23) |
| Los 5 bullets de Constraints | PROJECT.md «Constraints» (líneas 144-151), verbatim |

Los tres restos de encuadre de migración se van con ellos: «sin cambios» (Tech stack), «desde el día
1» (Security) e «igual que hoy» (Platform). PROJECT.md ya no los lleva.
</analysis>

<target_block>
El contenido EXACTO que debe quedar entre el principio del fichero y `<!-- GSD:project-end -->`,
ambos incluidos (el `-->` de cierre es la última línea del bloque; la línea 34 del fichero actual es
una línea en blanco y se conserva):

```markdown
<!-- GSD:project-start source:PROJECT.md -->

## Project

**Nyanko**

Nyanko es una app de escritorio (Windows) para trackear anime/manga: sincroniza
con AniList/MAL/Kitsu, escanea biblioteca local, detecta reproducción en curso,
sugiere torrents y trae una extensión companion de navegador. Es una app
gratuita orientada a comunidad. El shell de escritorio es Electron
(electron-vite: main + preload + renderer React/Vite) con un backend Python
(FastAPI) empaquetado como sidecar PyInstaller.

**Core Value:** Nyanko deja de ser solo un tracker y pasa a ser **donde
consumes**: el manga se lee dentro de la app, y el tracking ocurre solo — el
mismo trato que la detección de reproducción ya le da al anime.

### Constraints

- **Compatibility**: `userData` debe quedar en `%APPDATA%\app.nyanko.desktop`
  (identifier Tauri) o la biblioteca de prod existente queda huérfana. Hay un
  assert que crashea el arranque si se rompe.

- **Versionado**: el updater exige **semver estricto** — nada de sufijos
  `a`/`b`/`c`; los parches van `0.2.N`. Regla por versión: 0.2.x fixes /
  0.3.0+ features.

- **Tech stack**: electron-vite + electron-builder (NSIS) + electron-updater +
  TypeScript; sidecar Python PyInstaller onedir.

- **Security**: `contextIsolation:true`, `nodeIntegration:false`, `sandbox:true`,
  `webSecurity:true`.

- **Platform**: Windows es el target primario.

<!-- GSD:project-end -->
```
</target_block>

<tasks>

<task type="auto">
  <name>Tarea 1: Sustituir el bloque GSD:project-start por el texto de PROJECT.md</name>
  <files>.claude/CLAUDE.md</files>
  <action>
Con la herramienta **Edit**, sustituye en `.claude/CLAUDE.md` el bloque que va desde la primera línea
del fichero hasta `<!-- GSD:project-end -->` (líneas 1-33) por el contenido EXACTO de la sección
`<target_block>` de este plan. Cópialo carácter a carácter — está derivado de PROJECT.md, que es la
fuente de verdad; no reformules, no reescribas, no «mejores» la prosa.

Puntos que la sustitución tiene que respetar:

- Las dos líneas de marcador (`<!-- GSD:project-start source:PROJECT.md -->` y
  `<!-- GSD:project-end -->`) van BYTE-idénticas a como están hoy. Son los delimitadores del bloque:
  si se tocan, el bloque deja de ser localizable.
- El marcador de apertura sigue siendo la línea 1 del fichero.
- La línea en blanco que hoy separa `<!-- GSD:project-end -->` de
  `<!-- GSD:stack-start source:STACK.md -->` se conserva.

Prohibiciones DURAS de esta tarea (todas son decisiones ya tomadas por el usuario, no sugerencias):

- **NO ejecutes `gsd-tools generate-claude-md`** en ninguna de sus formas. Ignora `--dry-run` y
  escribe de verdad; regeneraría los siete bloques y triplicaría el fichero. Ver `<analysis>`.
- NO toques ningún otro bloque del fichero: Stack, Conventions, Architecture, Skills, Workflow
  Enforcement, Developer Profile. Quedan byte-idénticos.
- NO edites `.planning/PROJECT.md`. Es la fuente de la que copias y ya es correcta.
- NO toques `.planning/STACK.md` ni `.planning/research/STACK.md`.
- NO añadas un comentario de aviso dentro del bloque sobre que un `generate-claude-md` futuro lo
  pisaría. El tradeoff está conocido y aceptado.
- NO añadas contenido nuevo que PROJECT.md no tenga. Esto es una copia, no una redacción.
  </action>
  <verify>
    <automated>cd "E:/2023-09-04/anitracker/Nyanko" && [ "$(head -1 .claude/CLAUDE.md)" = '<!-- GSD:project-start source:PROJECT.md -->' ] && [ "$(grep -c 'GSD:project-start source:PROJECT.md' .claude/CLAUDE.md)" = 1 ] && [ "$(grep -c 'GSD:project-end' .claude/CLAUDE.md)" = 1 ] && ! grep -qE 'Tauri 2|engine-swap|Hoy el shell|sin cambios|desde el día 1|igual que hoy' .claude/CLAUDE.md && grep -q 'El shell de escritorio es Electron' .claude/CLAUDE.md && grep -q '\*\*Versionado\*\*' .claude/CLAUDE.md && grep -q 'el manga se lee dentro de la app' .claude/CLAUDE.md && diff <(git show HEAD:.claude/CLAUDE.md | sed -n '/GSD:stack-start/,$p') <(sed -n '/GSD:stack-start/,$p' .claude/CLAUDE.md) && echo VERDE</automated>
  </verify>
  <done>
El comando de verify imprime `VERDE`. Eso encadena las seis comprobaciones:

1. El marcador de apertura sigue siendo la línea 1.
2. Cada marcador aparece exactamente una vez (ni duplicado ni perdido).
3. Cero rastros del texto de 0.2 en TODO el fichero: la afirmación de Tauri, el bullet de engine-swap,
   y los tres restos de encuadre de migración.
4. Las tres afirmaciones nuevas están (shell Electron, bullet Versionado, core value de manga).
5. **La cola del fichero — los otros seis bloques, desde `GSD:stack-start` hasta el final — es
   byte-idéntica a HEAD.** Ésta es la comprobación que hace de gate real sobre «no toques nada más»:
   un `diff` vacío o falla. Es válida porque el árbol está limpio en HEAD (la escritura de
   `generate-claude-md` se revirtió).

`git diff --stat` debe listar UN solo fichero: `.claude/CLAUDE.md`.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| `.claude/CLAUDE.md` → contexto de cada sesión de agente | El fichero se inyecta como instrucciones con precedencia sobre el comportamiento por defecto. Su contenido ES superficie de instrucción: lo que diga, se obedece |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-tkj-01 | Tampering | bloque `GSD:project-start` | medium | mitigate | Es la amenaza que esta tarea CIERRA: instrucciones falsas inyectadas en cada sesión (scope 0.2 vs milestone 0.3) ya desviaron la planificación de la Fase 4. El texto se copia de PROJECT.md, la única fuente de verdad |
| T-tkj-02 | Tampering | los otros seis bloques del fichero | medium | mitigate | Una sustitución mal delimitada podría comerse bloques vecinos. El `diff` contra `HEAD` de la cola del fichero (desde `GSD:stack-start`) es un gate binario: cualquier byte cambiado fuera del bloque falla el verify |
| T-tkj-03 | Denial of Service | `gsd-tools generate-claude-md` | low | accept | Ejecutarlo inflaría CLAUDE.md de 84 a 284 líneas en cada sesión. Mitigado por prohibición explícita en el `<action>`, no por maquinaria — el usuario acepta que nada lo corre automáticamente |
</threat_model>

<verification>
1. **El gate mecánico:** el comando `<automated>` de la Tarea 1 imprime `VERDE`.
2. **Superficie mínima:** `git diff --stat` lista exactamente un fichero, `.claude/CLAUDE.md`.
3. **Lectura humana de 20 segundos:** el bloque nuevo describe la app que existe hoy (Electron, se lee
   manga dentro) y sus constraints son los cinco de PROJECT.md líneas 144-151.
4. **Comprobación negativa de que NO se corrió el comando prohibido:** `wc -l .claude/CLAUDE.md` da un
   número cercano a 84, no ~284. Si el fichero se ha triplicado, se ejecutó `generate-claude-md` y hay
   que revertir con `git checkout -- .claude/CLAUDE.md` y volver a hacerlo a mano.
</verification>

<success_criteria>
- [ ] El verify imprime `VERDE`
- [ ] El bloque afirma que el shell es Electron (electron-vite), no Tauri
- [ ] El core value inyectado es el de 0.3 (el manga se lee dentro de la app)
- [ ] El bullet **Scope** caducado ya no existe; en su sitio está **Versionado**
- [ ] Los cinco bullets de Constraints coinciden con PROJECT.md (Compatibility, Versionado, Tech stack, Security, Platform)
- [ ] Los dos marcadores, byte-idénticos y una sola vez cada uno
- [ ] La cola del fichero desde `GSD:stack-start` es byte-idéntica a HEAD (`diff` vacío)
- [ ] `git diff --stat` lista UN fichero
- [ ] `gsd-tools generate-claude-md` NO se ejecutó
- [ ] `.planning/PROJECT.md`, `.planning/STACK.md` y `research/STACK.md` sin tocar
</success_criteria>

<output>
Escribe `.planning/quick/260716-tkj-actualizar-la-seccion-project-de-claude-/260716-tkj-SUMMARY.md` al terminar.
</output>
