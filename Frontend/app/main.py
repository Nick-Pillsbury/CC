import argparse
import logging

import controller
import viewer


def main() -> None:
    parser = argparse.ArgumentParser(description="CC driver station")
    parser.add_argument("--kiosk", action="store_true", help="open the stream full screen")
    parser.add_argument("--no-view", action="store_true", help="don't open the stream")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    browser = None if args.no_view else viewer.open_stream(kiosk=args.kiosk)
    try:
        controller.run()
    except KeyboardInterrupt:
        pass
    finally:
        if browser:
            browser.terminate()


if __name__ == "__main__":
    main()
