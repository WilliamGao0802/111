"""测试环境隔离：在任何 core 模块被导入之前，把数据库指向临时目录。

用法：在每个测试模块的最顶部 `import _env  # noqa: F401`。
"""

import os
import tempfile
from pathlib import Path

if "BGL_DB_PATH" not in os.environ:
    _d = Path(tempfile.mkdtemp(prefix="bgl_test_"))
    os.environ["BGL_DB_PATH"] = str(_d / "test.db")
