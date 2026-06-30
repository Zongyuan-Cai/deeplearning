"""Sandbox — 代码执行环境。

警告：当前实现不是真正的沙箱。执行的代码具有与服务器进程相同的权限。
在生产环境中，应使用容器化（如 Docker）或其他沙箱技术来隔离代码执行。

提供 Python 代码执行能力，注入常用库和文件路径。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("app.agent.sandbox")

# 默认超时时间
DEFAULT_TIMEOUT = 30

# 最大输出大小
MAX_STDOUT_SIZE = 50000  # 50KB
MAX_STDERR_SIZE = 10000  # 10KB


def _generate_wrapper_code(code: str, files: list[dict[str, Any]] | None = None) -> str:
    """生成包装代码，注入常用库和文件路径。

    使用字符串拼接而不是 str.format()，避免用户代码中的大括号被误解。
    """
    files_json = json.dumps(files or [], ensure_ascii=False, default=str)

    # 使用字符串拼接而不是 format()
    wrapper = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Auto-generated sandbox wrapper

import sys
import json
import os
from pathlib import Path

# 尝试导入常用库
try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import csv
except ImportError:
    csv = None

import re
import collections
import itertools
import math
import statistics

# 注入文件路径变量
SESSION_FILES = ''' + files_json + '''
FILE_PATHS = {f["filename"]: f["path"] for f in SESSION_FILES if "filename" in f and "path" in f}

# 用户代码开始
''' + code + '''

'''
    return wrapper


def execute_code_sandbox(
    code: str,
    files: list[dict[str, Any]] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """在沙箱中执行 Python 代码。

    Args:
        code: 要执行的 Python 代码
        files: 当前会话的文件列表
        timeout: 超时时间（秒）

    Returns:
        包含执行结果的字典
    """
    # 生成包装代码
    wrapper_code = _generate_wrapper_code(code, files)

    # 使用配置的临时目录
    temp_dir = settings.TEMP_DIR
    os.makedirs(temp_dir, exist_ok=True)

    # 创建临时文件
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False,
            dir=temp_dir,
            encoding='utf-8'
        ) as f:
            f.write(wrapper_code)
            temp_path = f.name
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to create temp file: {str(e)}",
            "error_code": "TEMP_FILE_ERROR",
        }

    try:
        start_time = time.time()

        # 执行代码
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            # 限制环境变量，减少安全风险
            env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
                "HOME": os.environ.get("HOME", "/tmp"),
                "TEMP": temp_dir,
                "TMP": temp_dir,
            },
        )

        duration_ms = int((time.time() - start_time) * 1000)

        # 截断输出
        stdout = result.stdout[:MAX_STDOUT_SIZE] if result.stdout else ""
        stderr = result.stderr[:MAX_STDERR_SIZE] if result.stderr else ""

        return {
            "success": result.returncode == 0,
            "message": "Code executed successfully" if result.returncode == 0 else "Code execution failed",
            "data": {
                "stdout": stdout,
                "stderr": stderr,
                "returncode": result.returncode,
                "duration_ms": duration_ms,
            },
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": f"Code execution timed out after {timeout}s",
            "error_code": "TIMEOUT",
            "data": {
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "returncode": -1,
                "duration_ms": timeout * 1000,
            },
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "error_code": "EXECUTION_ERROR",
            "data": {
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
                "duration_ms": 0,
            },
        }
    finally:
        # 清理临时文件
        try:
            Path(temp_path).unlink(missing_ok=True)
        except Exception:
            pass
