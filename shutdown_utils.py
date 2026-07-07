# -*- coding: utf-8 -*-
import os
import tkinter as tk


def _coletar_widgets(widget):
    itens = [widget]
    try:
        for filho in widget.winfo_children():
            itens.extend(_coletar_widgets(filho))
    except Exception:
        pass
    return itens


def fechar_sistema(widget=None):
    candidatos = []
    try:
        if widget is not None:
            candidatos.append(widget)
    except Exception:
        pass

    try:
        default_root = tk._default_root  # type: ignore[attr-defined]
        if default_root is not None:
            candidatos.append(default_root)
    except Exception:
        pass

    vistos = set()
    for raiz in candidatos:
        if raiz is None:
            continue
        ident = id(raiz)
        if ident in vistos:
            continue
        vistos.add(ident)

        try:
            for after_id in raiz.tk.call("after", "info"):
                try:
                    raiz.after_cancel(after_id)
                except Exception:
                    pass
        except Exception:
            pass

        for w in _coletar_widgets(raiz):
            try:
                for after_id in w.tk.call("after", "info"):
                    try:
                        w.after_cancel(after_id)
                    except Exception:
                        pass
            except Exception:
                pass

    os._exit(0)
