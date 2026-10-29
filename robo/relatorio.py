"""Gera um PDF de "relatório de consulta" para fontes que não emitem documento próprio sem captcha
(Receita Federal – base aberta do CNPJ, e PGFN – base aberta da dívida ativa).

O PDF deixa claro que é um relatório gerado pelo robô da Carozzo a partir de fonte pública,
com data, fonte e link para conferência. Não é certidão oficial.
"""
import html

_browser = None
_pw = None


def _pagina():
    global _browser, _pw
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch()
    return _browser.new_page()


def fechar():
    global _browser, _pw
    if _browser is not None:
        try:
            _browser.close()
        finally:
            _pw.stop()
            _browser = _pw = None


def gerar(titulo, empresa, cnpj, linhas, fonte, link, gerado_em):
    e = html.escape
    corpo = "".join(f"<tr><th>{e(k)}</th><td>{e(str(v))}</td></tr>" for k, v in linhas if v not in (None, ""))
    doc = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>
      body {{ font-family: Arial, sans-serif; color: #1f2226; margin: 0; }}
      .topo {{ background: #04452f; color: #f4eee6; padding: 18px 28px; border-bottom: 4px solid #ab6d51; }}
      .topo b {{ letter-spacing: .3em; font-size: 15px; }} .topo span {{ float: right; font-size: 11px; letter-spacing: .15em; text-transform: uppercase; }}
      main {{ padding: 26px 28px; }}
      h1 {{ font-size: 20px; margin: 0 0 4px; font-weight: 600; }}
      .sub {{ color: #676a6d; font-size: 12px; margin-bottom: 18px; }}
      table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
      th, td {{ text-align: left; padding: 9px 10px; border-bottom: 1px solid #e1dcd3; vertical-align: top; }}
      th {{ width: 32%; color: #676a6d; font-weight: 600; }}
      .nota {{ margin-top: 22px; font-size: 11px; color: #676a6d; background: #f0ece5; padding: 10px 12px; border-radius: 6px; }}
    </style></head><body>
      <div class="topo"><b>CAROZZO</b><span>Controle de certidões</span></div>
      <main>
        <h1>{e(titulo)}</h1>
        <div class="sub">{e(empresa)} · CNPJ {e(cnpj)} · gerado em {e(gerado_em)}</div>
        <table>{corpo}</table>
        <div class="nota">Relatório de consulta gerado automaticamente a partir de fonte pública: {e(fonte)}.
          Não substitui certidão oficial. Conferência: {e(link)}</div>
      </main></body></html>"""
    p = _pagina()
    try:
        p.set_content(doc, wait_until="load")
        return p.pdf(format="A4", print_background=True, margin={"top": "0", "bottom": "12mm", "left": "0", "right": "0"})
    finally:
        p.close()
