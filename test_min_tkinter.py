# -*- coding: utf-8 -*-
"""Teste mínimo com tkinter para verificar PyInstaller"""
import tkinter as tk
from tkinter import messagebox

def main():
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("Teste", "Tkinter funcionando!")
    root.destroy()
    print("OK: tkinter executou com sucesso")
    return 0

if __name__ == "__main__":
    exit(main())
