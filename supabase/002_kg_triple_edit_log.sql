create table if not exists public.kg_triple_edit_log (
  edit_id bigserial primary key,
  vqa_id bigint not null references public.vqa(vqa_id) on delete cascade,
  old_triple_id bigint not null references public.kg_triple_catalog(triple_id),
  new_triple_id bigint not null references public.kg_triple_catalog(triple_id),
  edit_reason text,
  editor_note text,
  created_at timestamptz not null default now()
);