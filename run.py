import sys
import os

log_path = os.path.join(os.path.dirname(__file__), 'app.log')
log = open(log_path, 'a', encoding='utf-8')
sys.stdout = log
sys.stderr = log

print('=== 工具箱启动 ===')

from launcher import run
run()
