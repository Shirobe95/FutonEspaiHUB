-- Importación directa de 12 items faltantes E-2026-03
-- Ejecutar en Supabase SQL Editor si prefieres no usar el comando Python.
-- No toca WooCommerce ni stock.

insert into public.inventory_items (
    item_id,
    name,
    cubic_meters,
    rotation_c,
    packages,
    primary_supplier_price,
    pascal_price,
    family,
    subgroup,
    size,
    materials,
    commercial_status,
    heca_reference,
    woo_sku,
    notes,
    source
)
values
(780008,'Futón Duo y Látex · 90x200x16 cm',0.45,0.02,1,124.21,null,'Futones','Futón Duo y Látex','90x200x16 cm ','Látex','Normal','0780008',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 3.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(780010,'Futón Duo y Látex · 150x200x16 cm',0.75,0.03,1,193.01,null,'Futones','Futón Duo y Látex','150x200x16 cm','Látex','Normal','0780010',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 1.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(780014,'Futón Duo y Látex · 200x200x16 cm',0.33,0.01,1,254.61,null,'Futones','Futón Duo y Látex','200x200x16 cm','Látex','Normal','0780014',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 1.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(759005,'Futon Coco Plus · 90x200x14,5 cm',0.63,0.01,1,137.48,null,'Futones','f-1000 ( Futon Coco Plus)','90x200x14,5 cm','Coco','Normal','0759005',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 2.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(759006,'Futon Coco Plus · 120x200x14,5 cm',0.32,0.02,1,171.3,null,'Futones','f-1000 ( Futon Coco Plus)','120x200x14,5 cm','Coco','Normal','0759006',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 2.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(759007,'Futon Coco Plus · 140x200x14,5cm',0.7,0.02,1,199.85,null,'Futones','f-1000 ( Futon Coco Plus)','140x200x14,5cm','Coco','Normal','0759007',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 2.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(759008,'Futon Coco Plus · 140x190x14,5 cm',0.7,0.02,1,189.86,null,'Futones','f-1000 ( Futon Coco Plus)','140x190x14,5 cm','Coco','Normal','0759008',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 1.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(759009,'Futon Coco Plus · 180x200x14,5cm',0.81,0.01,1,256.95,null,'Futones','f-1000 ( Futon Coco Plus)','180x200x14,5cm','Coco','Normal','0759009',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 1.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(759010,'Futon Coco Plus · 200x200x14,5cm',0.9,0.01,1,285.5,null,'Futones','f-1000 ( Futon Coco Plus)','200x200x14,5cm','Coco','Normal','0759010',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 1.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(770002,'Futon Duo · 120x200x14,5 cm',0.54,0.02,1,76.23,null,'Futones','50 % Wool + 50% cotton ( 2 size)','120x200x14,5 cm','Algodón, Lana','Normal','0770002',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 2.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(770008,'Futon Duo· 200x200x14,5 cm',0.9,0.02,1,127.05,null,'Futones','50 % Wool + 50% cotton ( 2 size)','200x200x14,5 cm','Algodón, Lana','Normal','0770008',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 1.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03'),
(758087,'Premium (winter/summer) · 120x200x17 cm',0.33,0.02,1,159.08,null,'Otros','Premium (winter/summer)','120x200x17 cm',null,'Normal','0758087',null,'Import candidato desde PLANTILLA PEDIDO E-2026-03 + data.xlsx. Cantidad pedido: 1.0 Rotación C completada desde data.xlsx actualizado. Import SQL 12 faltantes E-2026-03.','import_excel_E-2026-03')
on conflict (item_id) do update
set
    name = excluded.name,
    cubic_meters = excluded.cubic_meters,
    rotation_c = excluded.rotation_c,
    packages = excluded.packages,
    primary_supplier_price = excluded.primary_supplier_price,
    pascal_price = excluded.pascal_price,
    family = excluded.family,
    subgroup = excluded.subgroup,
    size = excluded.size,
    materials = excluded.materials,
    commercial_status = excluded.commercial_status,
    heca_reference = excluded.heca_reference,
    woo_sku = excluded.woo_sku,
    notes = excluded.notes,
    source = excluded.source,
    updated_at = now();
