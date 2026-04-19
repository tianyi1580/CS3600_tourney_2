from pathlib import Path

def apply_replacements(text):
    # order matters!
    replacements = [
        ("yolanda_prime_v3_baseline", "yolanda_prime_v4_3"),
        ("yolanda_prime_v3", "yolanda_prime_v4_7"),
        ("YP3_", "YP4_"),
        ("yp3_", "yp4_"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text

files = [
    ("workflows/yp3_hyperopt.py", "workflows/yp4_hyperopt.py"),
    ("scripts/optimize_yp3_weights.py", "scripts/optimize_yp4_weights.py"),
    ("scripts/yp3_hyperopt_pace.slurm", "scripts/yp4_hyperopt_pace.slurm")
]

for src, dst in files:
    src_path = Path(src)
    dst_path = Path(dst)
    if src_path.exists():
        text = src_path.read_text()
        text = apply_replacements(text)
        dst_path.write_text(text)
        print(f"Created {dst}")
    else:
        print(f"Missing {src}")
