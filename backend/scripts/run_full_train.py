"""后台触发一次全量 train_all，并打印进度直至结束。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.training_service import training_service  # noqa: E402


def main():
    r = training_service.start_train_async()
    print(r, flush=True)
    if r.get("status") == "error":
        return 1
    while True:
        alive = training_service._train_thread and training_service._train_thread.is_alive()
        print(
            f"[{time.strftime('%H:%M:%S')}] "
            f"{training_service.training_progress}% "
            f"{training_service.training_message} "
            f"is_training={training_service.is_training} alive={alive}",
            flush=True,
        )
        if not training_service.is_training and not alive:
            break
        time.sleep(20)
    print("DONE", training_service.training_message, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
