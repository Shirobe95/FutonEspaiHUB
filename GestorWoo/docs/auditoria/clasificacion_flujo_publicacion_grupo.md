# Hallazgos de la auditoría vs. el flujo real de «Cambio de Precios»

Flujo real (confirmado por el usuario): Nueva propuesta → «Aplicar X cambios de precio» → preview → aplicar:
por cada línea, cambio en Woo y verificación posterior. Publican tanto admin como worker. Ya no se escribe «PUBLICAR».
Código: `preview_price_proposal_group` / `publish_price_proposal_group` (`cloud/services/woocommerce_publish.py`).

| Hallazgo | ¿Afecta al flujo real? | Estado en esta rama | Propuesta |
|---|---|---|---|
| W1 fechas de oferta ignoradas en `_effective_woo_price` | Sí, pero **decisión de negocio: se trabaja siempre con el precio vigente en Woo** y Futón Espai decide si tiene en cuenta ofertas programadas. | Sin cambio (decidido) | — |
| W2 `confirm`/rol | **No** (era del flujo individual y el CLI, no usados; además los workers pueden publicar). | Retirado del requisito | — |
| W3 bajada validada contra el espejo, no contra Woo vivo | Sí | **Corregido**: el preview de grupo compara aviso y bloqueo con el precio vivo de Woo (`_item_with_live_price`); 3 tests (espejo bajo/alto/aviso). La creación de propuestas ya usaba el precio vivo (`price_at_creation`). El flujo individual legacy no se usa y queda como estaba. | — |
| W4 `nan`/`inf` | Sí | **Corregido** (`money_or_none`, validadores de UI) | — |
| W5 WARNING publica sin confirmación; sin tope a subidas; sin comprobar `status` | Sí, pero **decisión de negocio**: los avisos se muestran en el preview y la decisión de publicar es de Futón Espai. | Sin cambio (decidido) | — |
| W6/W7/W8 fallos intermedios y rollback | Parcial: afectan a fallos a mitad de lote. | Sin cambio | Diario: revisar `except: pass` de los UPDATE de estado y el reintento del target ya fallido. |
| U2 cerrar ventana mientras publica | Sí | **Corregido** | — |
| D1 trazabilidad con kwargs inexistentes | Sí (constantes, proveedores, importación) | **Corregido** + test de contrato | — |
| D9 `packages` float | Sí (edición de inventario) | **Corregido** | — |
| U1 fuga entre usuarios tras logout | Sí | **Corregido** | — |
| U7 «3→5» mostrado «35» | Sí (preview de recepción) | **Corregido** | — |
| L4 `.env` con BOM/comentarios | Sí (afecta a lo que lee el ERP) | **Corregido** | Pendiente decidir si `.env` debe pisar variables de entorno reales (hoy las pisa). |
