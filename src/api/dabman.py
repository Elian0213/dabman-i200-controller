import requests
from requests.auth import HTTPBasicAuth

class DABMANi200:
    def __init__(self, ip, log_callback):
        self.ip = ip
        self.auth = HTTPBasicAuth("su3g4go6sk7", "ji39454xu/^")
        self.log = log_callback

    def req(self, path, port=80, timeout=15, silent=False):
        try:
            url = f"http://{self.ip}:{port}{path}"
            if not silent:
                self.log(f">>> REQ: GET {url}")

            headers = {"User-Agent": "curl/7.68.0"}
            r = requests.get(url, auth=self.auth, headers=headers, timeout=timeout)

            if 'image' in r.headers.get('Content-Type', '') or '.jpg' in path:
                if not silent:
                    self.log(f"<<< RES: [{r.status_code}] [Binary Image Data]")
                return r.content

            res_text = r.text.strip()
            display_text = res_text if len(res_text) < 500 else res_text[:500] + "\n...[TRUNCATED]"
            if not silent:
                self.log(f"<<< RES: [{r.status_code}]\n{display_text}")

            return r.text
        except requests.exceptions.ReadTimeout:
            if not silent:
                self.log("!!! ERR: Request timed out. The radio is responding too slowly.")
            return ""
        except Exception as e:
            if not silent:
                self.log(f"!!! ERR: {e}")
            return ""
