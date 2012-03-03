from gaesessions import SessionMiddleware
def webapp_add_wsgi_middleware(app):
    app = SessionMiddleware(app, cookie_key="0mv3oyqau9oyqamv3oyqau9oyqauu9oyqau9")
    return app