"""Start mitmweb proxy and print auth token for web UI."""
import sys
from mitmproxy.tools.main import mitmweb

# Disable web auth
sys.argv = ["mitmweb", "--listen-port", "8080", "--set", "web_auth=false"]
mitmweb()
