"""Download the official WebView2 SDK and extract the three x64 POC dependencies."""
from pathlib import Path
import hashlib
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "1.0.2903.40"
SHA256 = "ef128016dd1e51c59178c827ed5b8aa3322c57afa8675d930f8109505542ad74"
URL = f"https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/{VERSION}/microsoft.web.webview2.{VERSION}.nupkg"
FILES = (
    "lib/net462/Microsoft.Web.WebView2.Core.dll",
    "lib/net462/Microsoft.Web.WebView2.WinForms.dll",
    "runtimes/win-x64/native/WebView2Loader.dll",
)

def main():
    archive = ROOT / f"webview2-{VERSION}.nupkg"
    print("Downloading official Microsoft WebView2 SDK", VERSION, flush=True)
    with urllib.request.urlopen(URL, timeout=90) as response:
        data = response.read(100_000_001)
    if len(data) > 100_000_000 or hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("SDK size or SHA-256 does not match the pinned package")
    archive.write_bytes(data)
    target = ROOT / ".deps" / "webview2"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for name in FILES:
            (target / Path(name).name).write_bytes(package.read(name))
    print("SDK ready:", target)

if __name__ == "__main__":
    main()
