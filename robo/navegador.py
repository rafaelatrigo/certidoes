"""Um único navegador sem tela (Playwright) compartilhado pelo robô inteiro.
Abrir dois Playwright síncronos no mesmo processo dá erro, por isso tudo passa por aqui."""
_pw = None
_browser = None


def browser():
    global _pw, _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch()
    return _browser


def fechar():
    global _pw, _browser
    try:
        if _browser is not None:
            _browser.close()
    finally:
        if _pw is not None:
            _pw.stop()
        _pw = _browser = None
