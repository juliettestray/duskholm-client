"""Double-click launcher: runs Sanctuary without a console window."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sanctuary import main

main()
