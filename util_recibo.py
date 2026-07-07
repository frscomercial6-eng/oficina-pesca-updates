# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import os
from datetime import datetime

from fpdf import FPDF

from config import CAMINHO_BANCO, get_db_connection, enviar_arquivo_para_drive_usuario


TERMO_GARANTIA = (
    "TERMO DE GARANTIA: Fica assegurada a garantia de 90 (noventa) dias sobre os "
    "serviços executados e peças substituídas, contados a partir desta data de entrega, "
    "conforme o Código de Defesa do Consumidor."
)
MENSAGEM_ENTREGA = "MENSAGEM: Obrigado pela confiança! Sua carretilha está pronta para a próxima fisgada."


class ReciboPDF(FPDF):
    def header(self):
        pass

    def footer(self):
        pass


def _valor_float(valor):
    try:
        return float(valor or 0)
    except Exception:
        return 0.0


def _normalizar_id_os(dados_os):
    if isinstance(dados_os, dict):
        return int(dados_os.get("id") or dados_os.get("os_id") or 0)
    return int(dados_os[0]) if dados_os else 0


def _obter_dados_os(cursor, os_id):
    cursor.execute(
        """
        SELECT id, COALESCE(cliente,''), COALESCE(equipamento,''), COALESCE(defeito,''),
               COALESCE(valor_total,0), COALESCE(saldo,0), COALESCE(itens_detalhes,''),
               COALESCE(data,''), COALESCE(status,'')
        FROM orcamentos_aguardo
        WHERE id = ?
        """,
        (os_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"O.S. {os_id} nao encontrada para gerar recibo.")
    return row


def _obter_dados_oficina(cursor):
    cursor.execute(
        """
        SELECT COALESCE(nome_oficina,''), COALESCE(endereco_oficina,''), COALESCE(telefone_oficina,'')
        FROM dados_oficina
        WHERE id = 1
        """
    )
    row = cursor.fetchone() or ("", "", "")
    return row[0] or "OFICINA DE PESCA", row[1] or "", row[2] or ""


def _inserir_financeiro_entrega(cursor, os_id, cliente, valor_total, saldo, data_entrega):
    valor_lancamento = _valor_float(saldo) if _valor_float(saldo) > 0 else _valor_float(valor_total)
    if valor_lancamento <= 0:
        return

    descricao = f"ENTREGA O.S. {os_id} - {cliente}".strip()
    cursor.execute(
        """
        SELECT 1
        FROM fluxo_caixa
        WHERE UPPER(tipo) = 'ENTRADA'
          AND descricao = ?
        LIMIT 1
        """,
        (descricao,),
    )
    if cursor.fetchone() is not None:
        return

    cursor.execute(
        """
        INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento)
        VALUES (?, ?, 'ENTRADA', ?, ?, ?)
        """,
        (data_entrega, descricao, valor_lancamento, "ORDEM DE SERVICO", "ENTREGA"),
    )


def _montar_descricao_servicos(defeito, itens_detalhes):
    texto = (defeito or "").strip()
    itens_txt = ""
    if itens_detalhes:
        try:
            import json

            itens = json.loads(itens_detalhes)
            partes = []
            for item in itens:
                if not isinstance(item, (list, tuple)) or not item:
                    continue
                desc = str(item[0] or "").strip()
                qtd = str(item[1] or "1").strip() if len(item) > 1 else "1"
                if desc:
                    partes.append(f"{qtd}x {desc}" if qtd and qtd != "1" else desc)
            itens_txt = " / ".join(partes)
        except Exception:
            itens_txt = ""

    if texto and itens_txt:
        return f"{texto} | {itens_txt}"
    return texto or itens_txt or "Servicos executados conforme ordem de servico."


def _desenhar_bloco(pdf, y_top, via_titulo, dados):
    os_id, cliente, equipamento, descricao, valor_total, data_entrega, nome_oficina, endereco, telefone = dados
    margem = 10

    pdf.set_xy(margem, y_top)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(190, 7, "RECIBO DE ENTREGA - OFICINA DE PESCA", 0, 1, "L")

    pdf.set_x(margem)
    pdf.set_font("Arial", "", 9)
    pdf.cell(190, 5, via_titulo, 0, 1, "R")

    pdf.set_x(margem)
    pdf.set_font("Arial", "", 10)
    pdf.multi_cell(190, 5, f"Dados da Oficina: {nome_oficina} | {endereco} | {telefone}")

    pdf.set_x(margem)
    pdf.multi_cell(190, 5, f"Dados do Cliente: {cliente}")

    pdf.set_x(margem)
    pdf.multi_cell(190, 5, f"N OS: {os_id}   Data de Entrega: {data_entrega}")

    pdf.set_x(margem)
    pdf.multi_cell(190, 5, f"Equipamento: {equipamento}")

    pdf.set_x(margem)
    pdf.multi_cell(190, 5, f"Descricao dos Servicos: {descricao}")

    pdf.set_x(margem)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(190, 8, f"Valor Total: R$ {valor_total:.2f}", 0, 1, "L")

    pdf.set_x(margem)
    pdf.set_font("Arial", "", 9)
    pdf.multi_cell(190, 4.5, TERMO_GARANTIA)

    pdf.set_x(margem)
    pdf.multi_cell(190, 4.5, MENSAGEM_ENTREGA)

    y_ass = y_top + 125
    pdf.set_xy(margem, y_ass)
    pdf.cell(80, 6, "_______________________________", 0, 0, "L")
    pdf.cell(30, 6, "", 0, 0)
    pdf.cell(80, 6, "_______________________________", 0, 1, "L")

    pdf.set_x(margem)
    pdf.set_font("Arial", "", 8)
    pdf.cell(80, 4, "Assinatura do Tecnico", 0, 0, "L")
    pdf.cell(30, 4, "", 0, 0)
    pdf.cell(80, 4, "Assinatura do Cliente", 0, 1, "L")



def gerar_recibo_entrega(dados_os):
    """
    Gera recibo em A4 com duas vias identicas e linha de corte central,
    atualiza status para ENTREGUE e registra automaticamente no financeiro.
    """
    os_id = _normalizar_id_os(dados_os)
    if os_id <= 0:
        raise ValueError("Dados da O.S. invalidos para gerar recibo.")

    data_entrega = datetime.now().strftime("%d/%m/%Y")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        row = _obter_dados_os(cursor, os_id)
        os_id, cliente, equipamento, defeito, valor_total, saldo, itens_detalhes, _data, _status = row

        cursor.execute(
            """
            UPDATE orcamentos_aguardo
            SET status = 'ENTREGUE',
                status_entrega = 'ENTREGUE',
                data_entrega = ?,
                data_finalizacao = COALESCE(NULLIF(data_finalizacao, ''), ?)
            WHERE id = ?
            """,
            (data_entrega, data_entrega, os_id),
        )

        nome_oficina, endereco, telefone = _obter_dados_oficina(cursor)
        _inserir_financeiro_entrega(cursor, os_id, cliente, valor_total, saldo, data_entrega)
        conn.commit()

    descricao_servicos = _montar_descricao_servicos(defeito, itens_detalhes)

    pasta = os.path.join(os.path.dirname(CAMINHO_BANCO), "recibos_entrega")
    os.makedirs(pasta, exist_ok=True)
    caminho_pdf = os.path.join(pasta, f"Recibo_OS_{int(os_id):05d}.pdf")

    pdf = ReciboPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    dados_pdf = (
        int(os_id),
        str(cliente or ""),
        str(equipamento or ""),
        descricao_servicos,
        _valor_float(valor_total),
        data_entrega,
        nome_oficina,
        endereco,
        telefone,
    )

    _desenhar_bloco(pdf, 10, "VIA OFICINA", dados_pdf)
    _desenhar_bloco(pdf, 148, "VIA CLIENTE", dados_pdf)

    pdf.set_draw_color(110, 110, 110)
    pdf.set_line_width(0.4)
    pdf.line(10, 148, 200, 148)

    pdf.output(caminho_pdf)

    try:
        enviar_arquivo_para_drive_usuario(caminho_pdf, pasta_remota="Oficina de Pesca - PDFs")
    except Exception:
        pass

    try:
        if hasattr(os, "startfile"):
            os.startfile(caminho_pdf)  # type: ignore[attr-defined]
    except Exception:
        pass

    return caminho_pdf
