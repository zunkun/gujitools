# -*- coding: utf-8 -*-
"""支持 python -m desktop 与 hupper -m desktop 热重载开发。"""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
