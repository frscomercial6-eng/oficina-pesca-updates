# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import customtkinter as ctk
import webbrowser
import configparser
import os
from datetime import datetime
from version_info import VERSION
from core.i18n import t  # NOVO: import do sistema de i18n
from config import (
    obter_status_licenca,
    obter_chave_licenca_ativa,
    ja_teve_licenca_ativa,
    INFINITEPAY_LINK_MENSAL,
    INFINITEPAY_LINK_TRIMESTRAL,
    INFINITEPAY_LINK_SEMESTRAL,
    INFINITEPAY_LINK_ANUAL,
)


def _obter_info_licenca_runtime() -> tuple[str, str, str]:
    """Retorna status, validade (YYYY-MM-DD/PERMANENTE) e validade formatada para UI."""
    try:
        lic_ativa, _msg, _cliente, validade = obter_status_licenca()
        validade_txt = str(validade or "").strip()
        if not lic_ativa:
            return "EXPIRADO", validade_txt, validade_txt

        if validade_txt.upper() == "PERMANENTE":
            return "ATIVO", "PERMANENTE", "PERMANENTE"

        try:
            data_obj = datetime.strptime(validade_txt, "%Y-%m-%d")
            return "ATIVO", validade_txt, data_obj.strftime("%d/%m/%Y")
        except Exception:
            return "ATIVO", validade_txt, validade_txt
    except Exception:
        return "EXPIRADO", "", ""

def _obter_cfg_promo_runtime() -> tuple[bool, str, float, str]:
    """Lê a configuração da promoção de lançamento em tempo real."""
    try:
        from config import CAMINHO_CONFIG
        cfg_path = CAMINHO_CONFIG
        
        cfg = configparser.ConfigParser()
        if os.path.exists(cfg_path):
            cfg.read(cfg_path, encoding="utf-8")
            
        ativo = cfg.getboolean("pagamento", "promo_lancamento_ativo", fallback=True)
        nome = cfg.get("pagamento", "promo_lancamento_nome", fallback="PROMO LANÇAMENTO").strip()
        valor = cfg.getfloat("pagamento", "promo_lancamento_valor", fallback=49.90)
        link = cfg.get("pagamento", "infinitepay_link_promo_lancamento", 
                       fallback="https://checkout.infinitepay.io/frsoficinadepesca/y7qTEWlDj").strip()
        return ativo, nome, valor, link
    except Exception:
        return True, "PROMO LANÇAMENTO", 49.90, "https://checkout.infinitepay.io/frsoficinadepesca/y7qTEWlDj"


def janela_vendas(parent=None, forcar_abertura=False, dias_restantes_alerta=None):

    # Consulta direta ao banco para status, expiração e trava de promoção
    status, data_expiracao, data_expiracao_fmt = _obter_info_licenca_runtime()
    chave_ativa = obter_chave_licenca_ativa()
    # A promoção só aparece se NUNCA houve licença ativada (conta limpa)
    conta_limpa = not ja_teve_licenca_ativa()

    data_hoje = datetime.now().date()
    expirada = False
    dias_para_vencer = dias_restantes_alerta if isinstance(dias_restantes_alerta, int) else None
    # Lógica de bloqueio
    if status in ("ATIVO", "VIP") and data_expiracao and data_expiracao != "PERMANENTE":
        try:
            data_exp = datetime.strptime(data_expiracao, "%Y-%m-%d").date()
            dias_calculados = (data_exp - data_hoje).days
            if dias_para_vencer is None:
                dias_para_vencer = dias_calculados
            if data_hoje < data_exp:
                if not forcar_abertura:
                    return
            else:
                expirada = True
        except Exception:
            pass
    elif status in ("ATIVO", "VIP") and (not data_expiracao or data_expiracao == "PERMANENTE"):
        if not forcar_abertura:
            return
    elif status and status.upper() in ("EXPIRADO", "TRIAL"):
        if status.upper() == "EXPIRADO":
            expirada = True

    # --- LAYOUT E CORES ---

    # Cores e layout
    COR_FUNDO = "#181a1b"
    COR_TEXTO = "#f5f5f5"
    COR_BORDA_SUTIL = "#3b3b3b"
    COR_BORDA_DESTAQUE = "#FF9F43"
    COR_AZUL = "#2196f3"
    COR_LARANJA = "#FF9F43"
    COR_CINZA = "#3A3A4D"

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    root = ctk.CTkToplevel(parent) if parent else ctk.CTk()
    root.title(f"Planos de Assinatura - Oficina de Pesca v{VERSION}")
    root.minsize(1300, 750)
    root.configure(bg=COR_FUNDO)
    root.grab_set()
    try:
        root.state("zoomed")
    except Exception:
        try:
            root.attributes("-zoomed", True)
        except Exception:
            root.geometry("1300x750")


    if expirada and data_expiracao_fmt:
        ctk.CTkLabel(
            root,
            text=f"Sua licença expirou em {data_expiracao_fmt}. Escolha um plano abaixo para continuar utilizando o sistema.",
            font=("Roboto", 16, "bold"),
            text_color="#FF9F43",
            wraplength=1000,
            justify="center",
        ).pack(pady=(20, 5))

    ctk.CTkLabel(
        root,
        text=t("ui_escolha_o_melhor_plano_para_sua_oficina"),
        font=("Roboto", 28, "bold"),
        text_color=COR_TEXTO
    ).pack(pady=10 if expirada else 30)

    if isinstance(dias_para_vencer, int) and 0 <= dias_para_vencer <= 7 and not expirada:
        ctk.CTkLabel(
            root,
            text=f"Sua licença vence em {dias_para_vencer} dias. Aproveite para renovar agora!",
            font=("Roboto", 16, "bold"),
            text_color=COR_LARANJA,
            wraplength=1000,
            justify="center",
        ).pack(pady=(0, 10))

    main_frame = ctk.CTkFrame(root, fg_color=COR_FUNDO, corner_radius=0)
    main_frame.pack(expand=True, fill="both", padx=30, pady=20)

    promo_ativo, _, _, promo_link = _obter_cfg_promo_runtime()

    # Se a chave ativa for permanente (VIP), não mostrar nenhum botão de compra
    if chave_ativa and chave_ativa.strip() and ("PERMANENTE" in chave_ativa.upper() or "VIP" in (status or "").upper()):
        planos = []
    else:
        beneficios_padrao = [
            "✅ Acesso ao Sistema",
            "✅ Busca de Diagramas",
            "✅ Backup em Nuvem",
            "✅ Suporte",
        ]

        planos = []
        if promo_ativo and conta_limpa:  # Promo só aparece se nunca houve chave ativa
            planos.append({
                "nome": "PROMOCIONAL",
                "preco": "R$ 49,90",
                "slogan": "Oferta de Lançamento - 90 dias de uso (3 meses)",
                "beneficios": beneficios_padrao,
                "botao_cor": COR_AZUL,
                "botao_texto": "white",
                "border_width": 2,
                "border_color": "#00E676",
                "link": promo_link
            })
        planos.extend([
            {
                "nome": "MENSAL",
                "preco": "R$ 69,90",
                "slogan": "Acesso Imediato",
                "beneficios": beneficios_padrao,
                "botao_cor": COR_AZUL,
                "botao_texto": "white",
                "border_width": 1,
                "border_color": COR_BORDA_SUTIL,
                "link": INFINITEPAY_LINK_MENSAL,
            },
            {
                "nome": "TRIMESTRAL",
                "preco": "R$ 179,90",
                "slogan": "Ideal para começar",
                "beneficios": beneficios_padrao,
                "botao_cor": COR_AZUL,
                "botao_texto": "white",
                "border_width": 1,
                "border_color": COR_BORDA_SUTIL,
                "link": INFINITEPAY_LINK_TRIMESTRAL,
            },
            {
                "nome": "SEMESTRAL",
                "preco": "R$ 359,90",
                "slogan": "MELHOR ESCOLHA - Economize mais!",
                "tag": "MELHOR ESCOLHA",
                "beneficios": beneficios_padrao,
                "botao_cor": COR_LARANJA,
                "botao_texto": "black",
                "border_width": 3,
                "border_color": COR_BORDA_DESTAQUE,
                "link": INFINITEPAY_LINK_SEMESTRAL,
            },
            {
                "nome": "ANUAL",
                "preco": "R$ 799,90",
                "slogan": "VALOR PROFISSIONAL - 12 meses",
                "beneficios": beneficios_padrao,
                "botao_cor": COR_CINZA,
                "botao_texto": "white",
                "border_width": 3,
                "border_color": "#FFD700",
                "link": INFINITEPAY_LINK_ANUAL,
            }
        ])

    cards_frame = ctk.CTkScrollableFrame(
        main_frame,
        fg_color=COR_FUNDO,
        orientation="vertical",
    )
    cards_frame.pack(expand=True, fill="both", padx=10, pady=10)

    # Limita cards por linha para evitar esmagamento lateral em telas menores.
    cards_por_linha = 3
    for col in range(cards_por_linha):
        cards_frame.grid_columnconfigure(col, weight=1, minsize=340)

    for idx, plano in enumerate(planos):
        row = idx // cards_por_linha
        col = idx % cards_por_linha
        card = ctk.CTkFrame(
            cards_frame,
            width=300,
            height=700,
            fg_color=COR_FUNDO,
            border_color=plano["border_color"],
            border_width=plano["border_width"],
            corner_radius=22
        )
        card.grid(row=row, column=col, padx=20, pady=24, sticky="nsew")
        card.grid_propagate(False)

        # Frame interno para evitar corte visual nos cantos
        inner = ctk.CTkFrame(card, fg_color=COR_FUNDO, corner_radius=20)
        inner.pack(expand=True, fill="both", padx=20, pady=20)

        # Título
        ctk.CTkLabel(
            inner,
            text=plano["nome"],
            font=("Roboto", 18, "bold"),
            text_color=COR_TEXTO
        ).pack(pady=(10, 2))

        if plano.get("tag"):
            ctk.CTkLabel(
                inner,
                text=plano["tag"],
                font=("Roboto", 12, "bold"),
                text_color=COR_LARANJA,
            ).pack(pady=(0, 6))

        # Preço
        ctk.CTkLabel(
            inner,
            text=plano["preco"],
            font=("Roboto", 32, "bold"),
            text_color=COR_TEXTO
        ).pack(pady=(0, 5))

        # Slogan
        ctk.CTkLabel(
            inner,
            text=plano["slogan"],
            font=("Arial", 13, "italic"),
            text_color=COR_LARANJA if plano["nome"] == "SEMESTRAL" else "#bdbdbd",
            wraplength=230,
            width=240,
            justify="center",
            anchor="center",
        ).pack(pady=(0, 10), padx=10)

        # Benefícios
        for beneficio in plano["beneficios"]:
            ctk.CTkLabel(
                inner,
                text=beneficio,
                font=("Roboto", 12),
                text_color=COR_TEXTO,
                anchor="w",
                wraplength=230,
                width=240,
                justify="left",
            ).pack(fill="x", padx=10, pady=5)

        # Espaço para alinhar botões
        ctk.CTkLabel(inner, text="").pack(expand=True, fill="both")

        ctk.CTkButton(
            inner,
            text=t("ui_assinar_agora"),
            font=("Roboto", 15, "bold"),
            fg_color=plano["botao_cor"],
            text_color=plano["botao_texto"],
            corner_radius=20,
            height=40, width=180,
            command=lambda l=plano["link"]: webbrowser.open(l)
        ).pack(pady=(20, 20), side="bottom")

    if not parent:
        root.mainloop()