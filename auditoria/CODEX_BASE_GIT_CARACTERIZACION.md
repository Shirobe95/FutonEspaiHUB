# FutonHUB - Base Git para fase de caracterizacion

Fecha: 2026-06-14

## Rama activa

```text
## refactor/modularizacion-v1...origin/refactor/modularizacion-v1
```

## Ramas locales

```text
main                       6946d4e [origin/main] Add FutonHUB checkpoint v62.1 baseline
refactor/modularizacion-v1 6946d4e [origin/refactor/modularizacion-v1] Add FutonHUB checkpoint v62.1 baseline
```

## Ramas remotas

```text
origin/main                       6946d4e Add FutonHUB checkpoint v62.1 baseline
origin/refactor/modularizacion-v1 6946d4e Add FutonHUB checkpoint v62.1 baseline
```

## Commit base

```text
6946d4e9091208b61a3f43d28721fe7cb57c2a14
```

`main` y `refactor/modularizacion-v1` apuntan al mismo commit base:

```text
6946d4e Add FutonHUB checkpoint v62.1 baseline
```

## Diferencia actual entre `main` y `refactor/modularizacion-v1`

Comandos:

```powershell
git diff --stat main..refactor/modularizacion-v1
git diff --name-only main..refactor/modularizacion-v1
```

Resultado:

```text
Sin diferencias.
```

## Copias anidadas

Comprobaciones ejecutadas dentro del repositorio clonado:

```powershell
Get-ChildItem -Recurse -Force -Directory -Filter .git
Get-ChildItem -Recurse -Force -File -Filter CHECKPOINT_V62_1_CODEX.md
```

Resultado:

```text
Unico .git:
FutonEspaiHUB\.git

Unico checkpoint:
FutonEspaiHUB\CHECKPOINT_V62_1_CODEX.md
```

Conclusion: no existe una copia anidada ni una segunda importacion completa del proyecto dentro del repositorio de trabajo `FutonEspaiHUB`.

## Alcance autorizado

Solo queda autorizada la fase de caracterizacion:

1. Test del entrypoint y contrato de navegacion.
2. Tests de precio efectivo y payload Woo.
3. Tests de clasificacion, productos test, padres variables y enlaces.
4. Tests de persistencia de log y snapshot.
5. Tests de rollback real de `regular_price` y `sale_price`.
6. Tests de componentes de packs.

Restricciones:

- Usar dobles/mocks.
- No escribir en WooCommerce real.
- No escribir en Supabase real.
- No iniciar extraccion de UI compartida, shell, navegacion o modulos.
- Documentar bugs encontrados aparte y no corregirlos salvo que formen parte de la caracterizacion.

