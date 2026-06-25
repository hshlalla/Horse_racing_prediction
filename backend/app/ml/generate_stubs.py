import os

files_to_create = [
    "crawl/kra_client.py",
    "crawl/parsers/__init__.py",
    "crawl/parsers/race_card.py",
    "crawl/upsert.py",
    "crawl/pipeline.py",
    "features/asof.py",
    "features/builders/__init__.py",
    "features/builders/horse_form.py",
    "features/builders/jockey_trainer.py",
    "features/builders/pedigree.py",
    "features/builders/inrace.py",
    "features/builders/market.py",
    "features/builders/track_condition.py",
    "features/assemble.py",
    "train/dataset.py",
    "train/models/__init__.py",
    "train/models/lgbm_binary.py",
    "train/models/catboost_binary.py",
    "train/models/plackett_luce.py",
    "train/models/ensemble.py",
    "train/evaluate.py",
    "train/promote.py",
    "predict/calibration.py",
]

base_dir = "/Users/studio/Downloads/project/Horse_racing_prediction/backend/app/ml"

for file_path in files_to_create:
    full_path = os.path.join(base_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(f'"""\nStub for {file_path}\nFollows the architecture from the design doc.\n"""\n\n')
        f.write('def execute():\n    pass\n')

print("Created all ML stubs.")
