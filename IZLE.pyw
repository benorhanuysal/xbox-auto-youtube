# Bekciyi pencere olmadan calistirir (Windows acilisinda bu dosya calisir). Durdurmak icin:
# Gorev Yoneticisi > pythonw.exe. Ayrinti: python -m studyo.izle --help
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from studyo import izle  # noqa: E402

izle.main([])
