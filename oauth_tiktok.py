"""
oauth_tiktok.py — Setup inicial de l'OAuth de TikTok (executa UNA SOLA VEGADA).

Instruccions:
  1. Obre developers.tiktok.com i crea una app (o usa la que ja tens)
  2. A la secció "Products" activa:  Login Kit  +  Content Posting API
  3. A "Redirect URI" afegeix:  http://localhost:8080/callback
  4. Executa aquest script:
       python oauth_tiktok.py
  5. S'obrirà el navegador. Autoritza l'app amb el teu compte TikTok.
  6. Al final et mostrarà els 3 secrets per afegir a GitHub Actions.

NOTA: TikTok pot trigar dies a aprovar el permís video.publish per a
producció. Mentre l'app estigui en revisió, les publicacions van al Sandbox
(no surten al feed real). Per sol·licitar l'aprovació: ves al portal de
developers.tiktok.com > la teva app > "Audit".
"""

import http.server
import secrets
import sys
import urllib.parse
import webbrowser

import requests

print("─── Setup OAuth TikTok ───\n")
CLIENT_KEY = input("CLIENT_KEY de la teva app TikTok: ").strip()
CLIENT_SECRET = input("CLIENT_SECRET de la teva app TikTok: ").strip()

REDIRECT_URI = "http://localhost:8080/callback"
STATE = secrets.token_urlsafe(16)

SCOPES = "user.info.basic,video.upload,video.publish"

auth_url = (
    "https://www.tiktok.com/v2/auth/authorize/"
    "?client_key={}"
    "&response_type=code"
    "&scope={}"
    "&redirect_uri={}"
    "&state={}"
).format(CLIENT_KEY, SCOPES, urllib.parse.quote(REDIRECT_URI), STATE)

print("\nObrint el navegador per autoritzar l'app...")
print("URL: {}\n".format(auth_url))
webbrowser.open(auth_url)

# Servidor local per capturar el callback de TikTok
code_rebut = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            code_rebut.append(params["code"][0])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                b"<h1>Autoritzat correctament!</h1>"
                b"<p>Tanca aquesta pestanya i torna al terminal.</p>"
            )
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h1>Error: no s'ha rebut el codi.</h1>")

    def log_message(self, *args):
        pass


server = http.server.HTTPServer(("", 8080), Handler)
print("Esperant que TikTok faci el callback (port 8080)...")
while not code_rebut:
    server.handle_request()
server.server_close()

# Intercanviar el codi per tokens
print("\nIntercanviant codi per tokens...")
try:
    r = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code_rebut[0],
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    data = r.json()
except Exception as e:
    print("Error de xarxa: {}".format(e))
    sys.exit(1)

if data.get("error"):
    print("Error de TikTok: {} — {}".format(data.get("error"), data.get("error_description", "")))
    print("Resposta completa: {}".format(data))
    sys.exit(1)

refresh_token = data.get("refresh_token", "")
if not refresh_token:
    print("TikTok no ha retornat refresh_token: {}".format(data))
    sys.exit(1)

print("\n✓ Autenticació completada!\n")
print("=" * 60)
print("Afegeix aquests 3 secrets a GitHub Actions:")
print("  Repo: github.com/sergicas/promotor-avatar")
print("  Settings > Secrets and variables > Actions > New repository secret")
print("=" * 60)
print()
print("TIKTOK_CLIENT_KEY")
print(CLIENT_KEY)
print()
print("TIKTOK_CLIENT_SECRET")
print(CLIENT_SECRET)
print()
print("TIKTOK_REFRESH_TOKEN")
print(refresh_token)
print()
print("El refresh_token caduca al cap de 365 dies.")
print("Si caduca, torna a executar aquest script.")
