-- Schema SQL para provisionamento no Supabase
-- Execute este conteúdo no SQL Editor do painel do Supabase.

create extension if not exists pgcrypto;

create table if not exists public.usuarios (
    id uuid primary key default gen_random_uuid(),
    nome text not null,
    email text unique not null,
    senha_hash text,
    perfil text default 'usuario',
    ativo boolean default true,
    criado_em timestamptz default now()
);

create table if not exists public.clientes (
    id uuid primary key default gen_random_uuid(),
    nome text not null,
    cpf_cnpj text,
    telefone text,
    email text,
    endereco text,
    ativo boolean default true,
    criado_em timestamptz default now()
);

create table if not exists public.ordens_servico (
    id uuid primary key default gen_random_uuid(),
    numero text unique,
    cliente_id uuid references public.clientes(id) on delete set null,
    status text default 'aberta',
    valor_total numeric(12,2) default 0,
    observacoes text,
    criado_em timestamptz default now()
);

create table if not exists public.produtos_servicos (
    id uuid primary key default gen_random_uuid(),
    nome text not null,
    tipo text default 'servico',
    valor numeric(12,2) default 0,
    ativo boolean default true,
    criado_em timestamptz default now()
);
