from urllib.request import Request, urlopen

URL = "http://127.0.0.1:8001"


def call(path, method="GET"):
    request = Request(f"{URL}{path}", method=method)
    with urlopen(request) as response:
        return response.read().decode()


# print("Start:", call("/stream/start", "POST"))
# print("Status:", call("/status"))
# print("Stop:", call("/stream/stop", "POST"))
# print("Status:", call("/status"))


call("/stream/start", "POST")