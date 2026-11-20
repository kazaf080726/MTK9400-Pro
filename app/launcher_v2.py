# -*- coding: utf-8 -*-
"""V2 打包入口，同时兼容 --mtk 子进程客户端。"""
import os
import sys

if __name__ == "__main__":
    app_dir = os.path.dirname(os.path.abspath(__file__))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    if len(sys.argv) > 1 and sys.argv[1] == "--mtk":
        # MtkSession 通过当前 exe --mtk 启动 mtkclient server。
        # 必须在这里分发，否则子进程会再打开一次 GUI，COM 永远连不上。
        args = sys.argv[2:]
        sys.argv = ["mtk.py"] + args
        try:
            import mtk
            sys.exit(int(mtk.main() or 0))
        except SystemExit as e:
            sys.exit(int(e.code or 0))
        except Exception as e:
            import traceback
            print("MTK 操作异常: %s" % e)
            traceback.print_exc()
            sys.exit(1)
    from v2.main import main
    sys.exit(main())
