# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import os
import tempfile
from datetime import datetime
from tkinter import filedialog

from fpdf import FPDF

from config import CAMINHO_BANCO, get_db_connection, enviar_arquivo_para_drive_usuario
from core.financeiro.repository import obter_total_recebido_os, registrar_recebimentos_os


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
               COALESCE(data,''), COALESCE(status,''), COALESCE(status_entrega,'')
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


def _inserir_financeiro_entrega(cursor, os_id, cliente, pagamentos, valor_esperado, data_entrega):
    registrar_recebimentos_os(
        cursor,
        os_id,
        cliente,
        pagamentos,
        valor_esperado,
        "ENTREGA",
        data_entrega,
    )


def concluir_entrega_os(dados_os, pagamentos_entrega=None):
    """Confirma a entrega e grava os recebimentos em uma única transação."""
    os_id = _normalizar_id_os(dados_os)
    if os_id <= 0:
        raise ValueError("Identificador de O.S. invalido para confirmar a entrega.")

    data_entrega = datetime.now().strftime("%d/%m/%Y")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        row = _obter_dados_os(cursor, os_id)
        os_id, cliente, _equipamento, _defeito, valor_total, _saldo, _itens, _data, status, status_entrega = row
        status = str(status or "").strip().upper()
        status_entrega = str(status_entrega or "").strip().upper()
        if status == "EXCLUIDO":
            raise ValueError(f"A O.S. {os_id} esta arquivada e nao pode ser entregue.")
        if status == "ENTREGUE" or status_entrega == "ENTREGUE":
            cursor.execute(
                """
                UPDATE orcamentos_aguardo
                SET status = 'ENTREGUE',
                    status_entrega = 'ENTREGUE',
                    data_entrega = COALESCE(NULLIF(data_entrega, ''), ?)
                WHERE id = ?
                """,
                (data_entrega, os_id),
            )
            conn.commit()
            return False
        if status != "FINALIZADO":
            raise ValueError("Somente uma O.S. finalizada e aguardando retirada pode ser entregue.")

        recebido_centavos = obter_total_recebido_os(cursor, os_id)
        total_centavos = int(round(_valor_float(valor_total) * 100))
        pendente_centavos = max(0, total_centavos - recebido_centavos)
        pagamentos_entrega = list(pagamentos_entrega or [])
        if pendente_centavos:
            if not pagamentos_entrega:
                raise ValueError("Informe as formas e os valores recebidos antes de confirmar a entrega.")
            _inserir_financeiro_entrega(
                cursor,
                os_id,
                cliente,
                pagamentos_entrega,
                pendente_centavos / 100,
                data_entrega,
            )
        elif pagamentos_entrega:
            raise ValueError("A O.S. nao possui saldo pendente para receber.")

        cursor.execute(
            """
            UPDATE orcamentos_aguardo
            SET status = 'ENTREGUE',
                status_entrega = 'ENTREGUE',
                data_entrega = ?,
                data_finalizacao = COALESCE(NULLIF(data_finalizacao, ''), ?)
            WHERE id = ? AND UPPER(COALESCE(status, '')) = 'FINALIZADO'
            """,
            (data_entrega, data_entrega, os_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Nao foi possivel atualizar o status da O.S. {os_id}.")
        conn.commit()
        return True


def obter_valor_pendente_os(os_id, valor_total):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        recebido_centavos = obter_total_recebido_os(cursor, int(os_id))
    total_centavos = int(round(_valor_float(valor_total) * 100))
    return max(0, total_centavos - recebido_centavos) / 100


def salvar_recibo_com_dialogo(parent, dados_os):
    os_id = _normalizar_id_os(dados_os)
    caminho_pdf = filedialog.asksaveasfilename(
        parent=parent,
        title="Salvar recibo",
        initialdir=os.path.dirname(CAMINHO_BANCO),
        initialfile=f"Recibo_OS_{os_id:05d}.pdf",
        defaultextension=".pdf",
        filetypes=[("Arquivo PDF", "*.pdf")],
    )
    if not caminho_pdf:
        return None
    return gerar_recibo_entrega(dados_os, caminho_pdf)


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



def gerar_recibo_entrega(dados_os, caminho_pdf):
    """Gera um PDF de uma O.S. cuja entrega ja foi confirmada."""
    os_id = _normalizar_id_os(dados_os)
    caminho_pdf = str(caminho_pdf or "").strip()
    if os_id <= 0 or not caminho_pdf:
        raise ValueError("Dados da O.S. invalidos para gerar recibo.")
    caminho_pdf = os.path.abspath(caminho_pdf)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        row = _obter_dados_os(cursor, os_id)
        os_id, cliente, equipamento, defeito, valor_total, _saldo, itens_detalhes, data_entrega, status, _status_entrega = row
        if str(status or "").strip().upper() != "ENTREGUE":
            raise ValueError("Confirme a entrega da O.S. antes de gerar o recibo.")
        data_entrega = data_entrega or datetime.now().strftime("%d/%m/%Y")
        nome_oficina, endereco, telefone = _obter_dados_oficina(cursor)
        descricao_servicos = _montar_descricao_servicos(defeito, itens_detalhes)

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

        diretorio = os.path.dirname(caminho_pdf)
        if not os.path.isdir(diretorio):
            raise FileNotFoundError(f"O diretorio escolhido nao existe: {diretorio}")

        arquivo_temporario = tempfile.NamedTemporaryFile(
            prefix=".recibo_",
            suffix=".pdf",
            dir=diretorio,
            delete=False,
        )
        caminho_temporario = arquivo_temporario.name
        arquivo_temporario.close()
        try:
            pdf.output(caminho_temporario)
            if not os.path.isfile(caminho_temporario) or os.path.getsize(caminho_temporario) == 0:
                raise OSError("O arquivo PDF nao foi gravado corretamente.")
            with open(caminho_temporario, "rb") as arquivo:
                if arquivo.read(5) != b"%PDF-":
                    raise OSError("O arquivo gerado nao possui um cabecalho PDF valido.")
            os.replace(caminho_temporario, caminho_pdf)
        finally:
            if os.path.exists(caminho_temporario):
                os.remove(caminho_temporario)

        if not os.path.isfile(caminho_pdf) or os.path.getsize(caminho_pdf) == 0:
            raise OSError(f"Nao foi possivel confirmar a gravacao do recibo: {caminho_pdf}")

    try:
        enviar_arquivo_para_drive_usuario(caminho_pdf, pasta_remota="Oficina de Pesca - PDFs")
    except Exception:
        pass

    try:
        if hasattr(os, "startfile"):
            os.startfile(caminho_pdf)  # type: ignore[attr-defined]
    except OSError:
        pass

    return caminho_pdf
