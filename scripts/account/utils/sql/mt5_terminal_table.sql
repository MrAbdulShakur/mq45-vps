create table mt5_terminals (
  id text primary key,
  path text not null,
  in_use boolean default false,
  last_assigned timestamp with time zone default now()
);

insert into mt5_terminals (id, path, in_use)
select 'T' || i, 'C:\\MQ45\\Terminals\\T' || i || '\\terminal64.exe', false
from generate_series(1, 32) as s(i);