import time

from tera.storage import ObjectStore


def main():
    store = ObjectStore()
    for attempt in range(30):
        try:
            store.ensure_bucket()
            print("Document bucket is ready")
            return
        except Exception:
            if attempt == 29:
                raise
            time.sleep(2)


if __name__ == "__main__":
    main()
