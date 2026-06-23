"""
poda_imatges.py — Manté net el magatzem d'imatges del repositori.

Esborra de la carpeta img/ del repo les imatges de més de DIES dies. Com que
els posts es preparen com a molt un parell de dies abans de publicar-se, una
imatge de més de 5 dies ja s'ha publicat segur i es pot esborrar sense risc.

No depèn de Buffer: es basa en la marca de temps del nom del fitxer
(img/<mil·lisegons>-<nom>.png). S'executa al núvol després de preparar els
posts. Esborra via l'API Contents de GitHub (no cal git push).
"""

import os
import re
import time

import requests

REPO = os.environ.get("GH_IMG_REPO", "sergicas/promotor-avatar")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
DIES = 5


def main():
    if not TOKEN:
        print("[poda] sense GITHUB_TOKEN; no es poda res.")
        return
    llindar_ms = (time.time() - DIES * 86400) * 1000
    api = "https://api.github.com/repos/{}/contents/img".format(REPO)
    headers = {"Authorization": "Bearer " + TOKEN,
               "Accept": "application/vnd.github+json"}
    try:
        r = requests.get(api + "?per_page=100", headers=headers, timeout=30)
    except Exception as e:
        print("[poda] error llistant img/: {}".format(e))
        return
    if r.status_code != 200:
        print("[poda] no puc llistar img/ ({}): {}".format(r.status_code, r.text[:120]))
        return

    esborrades = 0
    for f in r.json():
        m = re.match(r"(\d{10,})-", f.get("name", ""))
        if not m:
            continue  # nom no reconegut: el deixem estar
        if int(m.group(1)) >= llindar_ms:
            continue  # massa recent: encara pot estar en ús
        try:
            d = requests.delete(
                "https://api.github.com/repos/{}/contents/{}".format(REPO, f["path"]),
                headers=headers,
                json={"message": "poda: imatge de més de {} dies".format(DIES), "sha": f["sha"]},
                timeout=30,
            )
            if d.status_code == 200:
                esborrades += 1
        except Exception:
            pass
    print("[poda] esborrades {} imatges de més de {} dies.".format(esborrades, DIES))


if __name__ == "__main__":
    main()
