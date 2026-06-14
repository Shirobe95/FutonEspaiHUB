# UI ERP - Cambio de Precios v5

## Objetivo

Ajustar el modulo de Cambio de Precios / Propuestas para que trabaje con la logica real definida para FutonHUB:

- El precio actual de trabajo es siempre el precio de WooCommerce (`woo_price`).
- Si el precio anterior es 0, el item queda como Warning, pero se permite asignar un nuevo precio porque puede ser un item nuevo.
- Si un item ya tenia precio y se baja a 0, negativo o supera el porcentaje de bajada bloqueante, la accion queda bloqueada.
- El porcentaje de bloqueo se lee desde configuracion (`price_drop_block_percent`) y queda visible como constante `PRICE_DROP_BLOCK_PERCENT` en Configuracion / Calculos.

## Cambios visuales

### Propuestas guardadas

Se quita la columna de Cambio medio del listado de propuestas. El listado queda con:

- Propuesta
- Items
- Suben
- Bajan
- Estado

Motivo: el cambio medio no se trabajara por ahora y ensuciaba la lectura.

### Modificar propuesta

Se mantiene una unica ventana para:

- crear nueva propuesta
- modificar propuesta existente

Si se abre como nueva propuesta, el listado derecho empieza vacio.

Si se abre para modificar, el listado derecho carga los items de esa propuesta.

### Footer de tablas

En las tablas de items y variaciones, las entradas ahora llevan label visible:

- Subida %
- Valor

Ya no se usa texto placeholder dentro del input como unica guia.

Regla:

- se usa Subida % o Valor
- nunca ambas a la vez

Si ambas tienen valor, se bloquea la accion.

### Modificar item incluido

El boton Modificar de un item incluido no abre otra ventana.

Flujo:

1. Selecciona el item para edicion.
2. Lo marca como item activo en la tabla.
3. Muestra sus variaciones debajo.
4. Si se vuelve a anadir el mismo item, aparece aviso para sobrescribir o cancelar.

Esto evita ventanas extra y mantiene el flujo compacto.

## Validacion de precio

Reglas actuales:

- Precio propuesto <= 0 => Critical, bloqueado.
- Precio anterior <= 0 y precio propuesto > 0 => Warning, permitido.
- Precio anterior > 0 y bajada >= `price_drop_block_percent` => Critical, bloqueado.
- Precio anterior > 0 y bajada menor al bloqueo => permitido, con validaciones futuras de warning si aplica.

## Aceptar propuesta

Aceptar propuesta significa que el usuario confirma que quiere aplicar los cambios.

Flujo nuevo:

1. Se revisa la propuesta.
2. Se marca como aprobada.
3. Se ejecuta publicacion WooCommerce mediante el flujo protegido existente.
4. Se generan snapshot y audit log.
5. La propuesta queda publicada si WooCommerce responde correctamente.

La logica sigue protegida por:

- preview interno del servicio de publicacion
- bloqueo por errores rojos
- confirmacion interna `PUBLICAR`
- snapshot
- audit log
- lock de publicacion WooCommerce

## Rechazar propuesta

Rechazar no toca WooCommerce.

Solo marca la propuesta como rechazada y registra log.

## Configuracion

Se agrega en Configuracion / Calculos:

- `PRICE_DROP_BLOCK_PERCENT`
- descripcion: Bajada maxima de precio antes de bloquear
- unidad: %

Este valor representa el porcentaje maximo permitido de bajada antes de bloquear el cambio.

## Verificacion

Comandos ejecutados:

```bash
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```
