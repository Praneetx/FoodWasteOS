-- FoodWasteOS canonical schema (MVP v0.1)
-- Apply in Supabase SQL editor or with psql. Idempotent.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Tenants
-- ---------------------------------------------------------------------------
create table if not exists restaurants (
    id                uuid primary key default gen_random_uuid(),
    name              text        not null,
    location          text,
    timezone          text        not null default 'Asia/Kolkata',
    currency          char(3)     not null default 'INR',
    default_unit_cost numeric(10, 2) check (default_unit_cost is null or default_unit_cost >= 0),
    created_at        timestamptz not null default now()
);

create table if not exists users (
    id            uuid primary key,                 -- equals auth.users.id
    restaurant_id uuid not null references restaurants (id) on delete cascade,
    name          text,
    email         text not null,
    role          text not null default 'owner'
                  check (role in ('owner', 'manager', 'staff')),
    created_at    timestamptz not null default now()
);

create index if not exists users_restaurant_idx on users (restaurant_id);

-- ---------------------------------------------------------------------------
-- Catalogue
-- ---------------------------------------------------------------------------
create table if not exists food_items (
    id                uuid primary key default gen_random_uuid(),
    restaurant_id     uuid not null references restaurants (id) on delete cascade,
    name              text not null,
    preparation_unit  text not null default 'plate',
    batch_size        numeric(8, 2) not null default 1 check (batch_size > 0),
    unit_cost         numeric(10, 2) check (unit_cost is null or unit_cost >= 0),
    is_active         boolean not null default true,
    created_at        timestamptz not null default now(),
    unique (restaurant_id, name)
);

create index if not exists food_items_restaurant_idx on food_items (restaurant_id);

-- ---------------------------------------------------------------------------
-- Facts
-- ---------------------------------------------------------------------------
create table if not exists daily_sales (
    id                uuid primary key default gen_random_uuid(),
    restaurant_id     uuid not null references restaurants (id) on delete cascade,
    food_item_id      uuid not null references food_items (id) on delete cascade,
    sale_date         date not null,
    quantity_sold     integer not null default 0 check (quantity_sold >= 0),
    prepared_quantity integer check (prepared_quantity is null or prepared_quantity >= 0),
    promotion         boolean not null default false,
    stockout          boolean not null default false,
    notes             text,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    unique (food_item_id, sale_date)
);

create index if not exists daily_sales_restaurant_date_idx
    on daily_sales (restaurant_id, sale_date);
create index if not exists daily_sales_item_date_idx
    on daily_sales (food_item_id, sale_date);

create table if not exists food_waste (
    id               uuid primary key default gen_random_uuid(),
    restaurant_id    uuid not null references restaurants (id) on delete cascade,
    food_item_id     uuid not null references food_items (id) on delete cascade,
    waste_date       date not null,
    quantity_wasted  numeric(8, 2) not null check (quantity_wasted > 0),
    reason           text not null
                     check (reason in ('overproduction', 'unsold', 'spoilage', 'expired', 'other')),
    notes            text,
    created_at       timestamptz not null default now(),
    unique (food_item_id, waste_date, reason)
);

create index if not exists food_waste_restaurant_date_idx
    on food_waste (restaurant_id, waste_date);

-- ---------------------------------------------------------------------------
-- Prediction artefacts
-- ---------------------------------------------------------------------------
create table if not exists model_runs (
    id                uuid primary key default gen_random_uuid(),
    restaurant_id     uuid not null references restaurants (id) on delete cascade,
    model_type        text not null,              -- weekday_average_v1 | rf_v1 | ...
    trained_at        timestamptz not null default now(),
    train_start       date,
    train_end         date,
    mae               numeric(10, 3),
    wape              numeric(8, 4),
    bias              numeric(10, 3),
    params            jsonb not null default '{}'::jsonb,
    artifact_path     text
);

create index if not exists model_runs_restaurant_idx
    on model_runs (restaurant_id, trained_at desc);

create table if not exists forecasts (
    id                      uuid primary key default gen_random_uuid(),
    restaurant_id           uuid not null references restaurants (id) on delete cascade,
    food_item_id            uuid not null references food_items (id) on delete cascade,
    target_date             date not null,
    predicted_demand        numeric(10, 2) not null check (predicted_demand >= 0),
    lower_bound             numeric(10, 2),
    upper_bound             numeric(10, 2),
    recommended_preparation numeric(10, 2) not null check (recommended_preparation >= 0),
    confidence              text not null check (confidence in ('high', 'medium', 'low')),
    model_version           text not null,
    method                  text not null,
    sample_size             integer not null default 0,
    generated_at            timestamptz not null default now(),
    unique (food_item_id, target_date),
    check (lower_bound is null or upper_bound is null or lower_bound <= upper_bound)
);

create index if not exists forecasts_restaurant_date_idx
    on forecasts (restaurant_id, target_date);

-- ---------------------------------------------------------------------------
-- Optional defense-in-depth: Supabase RLS for direct client access.
-- The API uses a role that bypasses RLS and enforces tenant scope itself.
-- ---------------------------------------------------------------------------
-- alter table daily_sales enable row level security;
-- create policy tenant_read on daily_sales for select
--     using (restaurant_id = (auth.jwt() ->> 'restaurant_id')::uuid);
