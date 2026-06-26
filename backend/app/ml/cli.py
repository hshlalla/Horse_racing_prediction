import argparse
import sys

def crawl(args):
    print(f"Starting crawl since {args.since}...")
    import logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    from app.ml.crawl.pipeline import execute
    import asyncio
    execute()
    print("Crawl complete.")

def train(args):
    print(f"Starting training for track {args.track}...")
    from app.ml.train import evaluate
    evaluate.execute()
    print("Training complete.")

def predict(args):
    print(f"Generating predictions for race {args.race_id}...")
    # Calls app.ml.predict.service.predict_race()
    print("Prediction complete.")

def main():
    parser = argparse.ArgumentParser(description="Horse Racing ML Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl_parser = subparsers.add_parser("crawl", help="Crawl KRA data")
    crawl_parser.add_argument("--since", type=str, default="1990-01-01", help="Date to start crawling from (YYYY-MM-DD)")

    train_parser = subparsers.add_parser("train", help="Train the models")
    train_parser.add_argument("--track", type=str, required=True, choices=["SEOUL", "BUSAN", "JEJU"], help="Track to train models for")

    predict_parser = subparsers.add_parser("predict", help="Predict a specific race")
    predict_parser.add_argument("--race-id", type=int, required=True, help="ID of the race to predict")

    args = parser.parse_args()

    if args.command == "crawl":
        crawl(args)
    elif args.command == "train":
        train(args)
    elif args.command == "predict":
        predict(args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
