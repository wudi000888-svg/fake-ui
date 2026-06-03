#!/usr/bin/env python3
from hy2_sync import sync_hy2
from panel_config import QUOTA_COLLECT_CMD
from sync_utils import run_shell
from user_store import active_users
from xray_sync import sync_xray


def main():
    code, out = run_shell(QUOTA_COLLECT_CMD, timeout=60)
    if out.strip():
        print(out.strip())

    users = active_users()
    print("有效用户：", ",".join(users.keys()) if users else "无")

    sync_xray(users)
    sync_hy2(users)


if __name__ == "__main__":
    main()
