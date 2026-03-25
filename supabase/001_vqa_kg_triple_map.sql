alter table public.vqa
  add column if not exists triples_retrieved jsonb not null default '[]'::jsonb;

begin;

-- 1) Extend kg_triple_catalog for review + inline triple edit lineage
alter table public.kg_triple_catalog
  add column if not exists is_checked boolean not null default false,
  add column if not exists is_drop boolean not null default false,
  add column if not exists created_from text not null default 'import',
  add column if not exists parent_triple_id bigint,
  add column if not exists needs_review boolean not null default true;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'kg_triple_catalog_parent_triple_fk'
  ) then
    alter table public.kg_triple_catalog
      add constraint kg_triple_catalog_parent_triple_fk
      foreign key (parent_triple_id)
      references public.kg_triple_catalog(triple_id)
      on delete set null;
  end if;
end $$;

create index if not exists kg_triple_catalog_review_state_idx
  on public.kg_triple_catalog(is_checked, is_drop);

create index if not exists kg_triple_catalog_parent_triple_idx
  on public.kg_triple_catalog(parent_triple_id);

create index if not exists kg_triple_catalog_needs_review_idx
  on public.kg_triple_catalog(needs_review);

-- 2) Extend vqa for new retrieval + verify fields
alter table public.vqa
  add column if not exists triples_retrieved jsonb not null default '[]'::jsonb,
  add column if not exists q0_score integer,
  add column if not exists q1_score integer,
  add column if not exists q2_score integer,
  add column if not exists verify_decision text,
  add column if not exists verify_notes text,
  add column if not exists verify_rule text;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'vqa_q0_score_check'
  ) then
    alter table public.vqa
      add constraint vqa_q0_score_check
      check (q0_score is null or q0_score between 1 and 4);
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'vqa_q1_score_check'
  ) then
    alter table public.vqa
      add constraint vqa_q1_score_check
      check (q1_score is null or q1_score between 1 and 4);
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'vqa_q2_score_check'
  ) then
    alter table public.vqa
      add constraint vqa_q2_score_check
      check (q2_score is null or q2_score between 1 and 4);
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'vqa_verify_decision_check'
  ) then
    alter table public.vqa
      add constraint vqa_verify_decision_check
      check (verify_decision is null or verify_decision in ('KEEP', 'DROP'));
  end if;
end $$;

create index if not exists vqa_verify_decision_idx
  on public.vqa(verify_decision);

-- 3) Mapping table: VQA <-> KG triple
create table if not exists public.vqa_kg_triple_map (
  vqa_id bigint not null references public.vqa(vqa_id) on delete cascade,
  triple_id bigint not null references public.kg_triple_catalog(triple_id) on delete cascade,

  is_used boolean not null default false,
  is_retrieved boolean not null default false,
  is_active_for_vqa boolean not null default true,

  triple_review_status text,
  triple_review_note text,

  used_order integer,
  retrieval_rank integer,
  retrieved_from_food_items jsonb not null default '[]'::jsonb,

  replaced_by_triple_id bigint references public.kg_triple_catalog(triple_id) on delete set null,
  reviewed_from_page text,
  reviewed_at timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  primary key (vqa_id, triple_id)
);

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'vqa_kg_triple_map_status_check'
  ) then
    alter table public.vqa_kg_triple_map
      add constraint vqa_kg_triple_map_status_check
      check (
        triple_review_status is null
        or triple_review_status in ('valid', 'invalid', 'needs_edit', 'unsure')
      );
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'vqa_kg_triple_map_reviewed_from_page_check'
  ) then
    alter table public.vqa_kg_triple_map
      add constraint vqa_kg_triple_map_reviewed_from_page_check
      check (
        reviewed_from_page is null
        or reviewed_from_page in ('vqa_page', 'triple_page')
      );
  end if;
end $$;

create index if not exists vqa_kg_triple_map_vqa_idx
  on public.vqa_kg_triple_map(vqa_id);

create index if not exists vqa_kg_triple_map_triple_idx
  on public.vqa_kg_triple_map(triple_id);

create index if not exists vqa_kg_triple_map_status_idx
  on public.vqa_kg_triple_map(triple_review_status);

create index if not exists vqa_kg_triple_map_active_idx
  on public.vqa_kg_triple_map(is_active_for_vqa);

create index if not exists vqa_kg_triple_map_used_retrieved_idx
  on public.vqa_kg_triple_map(is_used, is_retrieved);

create index if not exists vqa_kg_triple_map_replaced_by_idx
  on public.vqa_kg_triple_map(replaced_by_triple_id);

-- 4) Audit log for inline triple edits
create table if not exists public.kg_triple_edit_log (
  edit_id bigserial primary key,
  vqa_id bigint not null references public.vqa(vqa_id) on delete cascade,
  old_triple_id bigint not null references public.kg_triple_catalog(triple_id) on delete restrict,
  new_triple_id bigint not null references public.kg_triple_catalog(triple_id) on delete restrict,
  edit_reason text,
  editor_note text,
  created_at timestamptz not null default now()
);

create index if not exists kg_triple_edit_log_vqa_idx
  on public.kg_triple_edit_log(vqa_id);

create index if not exists kg_triple_edit_log_old_triple_idx
  on public.kg_triple_edit_log(old_triple_id);

create index if not exists kg_triple_edit_log_new_triple_idx
  on public.kg_triple_edit_log(new_triple_id);

commit;