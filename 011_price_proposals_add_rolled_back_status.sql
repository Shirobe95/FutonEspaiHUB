-- FutonHUB v61.1
-- Amplía el estado permitido de propuestas para registrar rollback real.
-- Reejecutable.

alter table public.price_change_proposals
  drop constraint if exists price_change_proposals_status_check;

alter table public.price_change_proposals
  add constraint price_change_proposals_status_check
  check (status in (
    'pending',
    'approved',
    'publishing',
    'rejected',
    'published',
    'rolled_back',
    'error',
    'cancelled'
  ));
