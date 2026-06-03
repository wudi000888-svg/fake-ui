#!/usr/bin/env python3
import backup_manager
import audit_log


def main():
    result = backup_manager.create_backup(reason="scheduled")
    audit_log.write("system", "backup.scheduled", result["path"])
    print(result["path"])


if __name__ == "__main__":
    main()
