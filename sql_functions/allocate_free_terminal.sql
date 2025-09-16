create or replace function allocate_free_terminal()
returns table (
  id text,
  path text
)
language plpgsql
as $$
declare
  term record;
begin
  -- Lock one free terminal
  select * into term
  from terminals
  where in_use = false
  order by last_assigned nulls first
  limit 1
  for update skip locked;

  if not found then
    return;
  end if;

  -- Mark it as in use
  update terminals
  set in_use = true,
      last_assigned = now()
  where terminals.id = term.id;  -- ✅ Fully qualify the table column

  -- Return the allocated terminal
  return query select term.id, term.path;
end;
$$;
