import os
import sys

sys.path.insert(0, os.path.abspath('.'))

from ai.router import generate_copilot_response

try:
    print(generate_copilot_response("Hello, what is 2+2?", {}))
except Exception as e:
    print("FAILED:", e)
