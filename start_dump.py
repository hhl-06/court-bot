"""Start mitmdump and save all traffic to a text file."""
import sys
sys.argv = ["mitmdump", "--listen-port", "8080", "--flow-detail", "4"]
from mitmproxy.tools.main import mitmdump
mitmdump()
