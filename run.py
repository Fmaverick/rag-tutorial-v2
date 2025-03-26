import os
import sys

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from web.app import app

if __name__ == '__main__':
    app.run(debug=True, port=8000) 