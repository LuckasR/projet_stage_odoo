import subprocess
import re
import requests


CLOUD_FLARE_COMMAND = [
    "cloudflared",
    "tunnel",
    "--url",
    "http://localhost:8069"
]

SERVER_URL = "http://127.0.0.1:8000/api/tunnel"


def start_cloudflare_tunnel():
    try:
        print("🚀 Démarrage du tunnel Cloudflare...")

        process = subprocess.Popen(
            CLOUD_FLARE_COMMAND,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        tunnel_url = None

        for line in process.stdout:
            print("[cloudflared]", line, end="")

            match = re.search(
                r"https://[a-zA-Z0-9-]+\.trycloudflare\.com",
                line
            )

            if match:
                tunnel_url = match.group(0)

                print(f"\n✅ Tunnel trouvé : {tunnel_url}")

                try:
                    response = requests.post(
                        SERVER_URL,
                        json={
                            "url": tunnel_url
                        },
                        timeout=10
                    )

                    response.raise_for_status()

                    print("✅ URL envoyée au serveur")
                    print("Réponse :", response.text)

                except requests.RequestException as e:
                    print(f"❌ Erreur lors de l'envoi au serveur : {e}")

                # On a trouvé l'URL.
                # Le processus cloudflared doit continuer à tourner.
                break

        return process, tunnel_url

    except FileNotFoundError:
        print(
            "❌ cloudflared n'est pas installé "
            "ou n'est pas présent dans le PATH."
        )
        return None, None

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return None, None


if __name__ == "__main__":
    process, tunnel_url = start_cloudflare_tunnel()

    if tunnel_url:
        print(f"\n🌐 API accessible via : {tunnel_url}")

        # Garder Cloudflare Tunnel actif
        process.wait()