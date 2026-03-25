alter table public.vqa
  add column if not exists triples_retrieved jsonb not null default '[]'::jsonb;

create table if not exists public.vqa_kg_triple_map (
  vqa_id bigint not null references public.vqa(vqa_id) on delete cascade,
  triple_id bigint not null references public.kg_triple_catalog(triple_id) on delete cascade,
  is_used boolean not null default false,
  is_retrieved boolean not null default false,
  used_order integer,
  retrieval_rank integer,
  retrieved_from_food_items jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (vqa_id, triple_id)
);

create index if not exists vqa_kg_triple_map_vqa_idx
  on public.vqa_kg_triple_map(vqa_id);

create index if not exists vqa_kg_triple_map_triple_idx
  on public.vqa_kg_triple_map(triple_id);

create index if not exists vqa_kg_triple_map_used_idx
  on public.vqa_kg_triple_map(vqa_id, is_used);

create index if not exists vqa_kg_triple_map_retrieved_idx
  on public.vqa_kg_triple_map(vqa_id, is_retrieved);