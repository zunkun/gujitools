# -*- coding: utf-8 -*-
"""支持 python -m desktop 与 hupper -m desktop 热重载开发。"""

import sys

from desktop.app import main

if __name__ == "__main__":
    sys.exit(main())
