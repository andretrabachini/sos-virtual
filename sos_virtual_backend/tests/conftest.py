# permite rodar `py -m pytest` de dentro de sos_virtual_backend e importar os módulos do projeto
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
