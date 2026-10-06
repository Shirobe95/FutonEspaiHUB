INSERT INTO auth.users(id,email) VALUES
('aaaaaaaa-0000-0000-0000-000000000001','admin@lab.test'),
('bbbbbbbb-0000-0000-0000-000000000002','worker@lab.test'),
('cccccccc-0000-0000-0000-000000000003','inactive@lab.test');
INSERT INTO profiles(id,email,role,active) VALUES
('aaaaaaaa-0000-0000-0000-000000000001','admin@lab.test','admin',true),
('bbbbbbbb-0000-0000-0000-000000000002','worker@lab.test','worker',true),
('cccccccc-0000-0000-0000-000000000003','inactive@lab.test','worker',false);
INSERT INTO inventory_items(item_id,name,woo_id,woo_link_status,weighted_average_cost,primary_supplier_price,hub_item_code,source_row) VALUES
(1,'Item uno',1001,'Enlazado',10.5,'12.00','HUB1','{"k":1}'),(2,'Item dos',1002,'Enlazado',20,'25','HUB2','{}'),
(-900001,'TEST_WORKER_INVENTORY_ITEM',NULL,'Sin enlazar',NULL,NULL,NULL,'{"test":"true"}');
INSERT INTO inventory_item_components(parent_item_code,component_item_code,quantity,relation_type) VALUES('HUB1','HUB2',2,'component');
INSERT INTO inventory_stock_reset_backups(run_id,source_name,stock_field,item_id,old_store_stock) VALUES(gen_random_uuid(),'t','store','1',5);
INSERT INTO price_change_proposals(id,item_kind,item_woo_id,name,old_price,new_price,status,source_row,local_sqlite_id) VALUES
('11111111-1111-1111-1111-111111111111','product',1001,'P1',10,12,'pending','{"a":1}',1),
('22222222-2222-2222-2222-222222222222','product',1002,'P2',10,12,'approved','{}',2);
INSERT INTO business_constants(key,value) VALUES('PRICE_DROP_BLOCK_PERCENT','60');
INSERT INTO supplier_prices(item_id,supplier,price) VALUES(1,'S1','9.9');
INSERT INTO audit_logs(operation_id,module,action,status,user_email,role) VALUES('op-seed','m','a','OK','admin@lab.test','admin');
INSERT INTO operation_snapshots(operation_id,module,action,entity_type,entity_id,before_data) VALUES('op-seed','m','a','t','1','{"secret":"x"}');
INSERT INTO supplier_orders(order_id,provider,order_file,source_row) VALUES('33333333-3333-3333-3333-333333333333','S1','TEST_WORKER_ORDER','{"test":"true"}');
INSERT INTO system_locks(operation_key,locked_by,expires_at,status) VALUES('seedlock','aaaaaaaa-0000-0000-0000-000000000001',now()+interval '10 min','running');
