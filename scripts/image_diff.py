#!/usr/bin/env python3
import argparse
import json
import os
import time

from PIL import Image, ImageChops, ImageEnhance, ImageStat


def _load_image(path):
    img = Image.open(path)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    return img


def _diff_stats(diff_img):
    diff_l = diff_img.convert("L")
    hist = diff_l.histogram()
    total = sum(hist)
    if total <= 0:
        return {
            "mean_abs": 0.0,
            "max_abs": 0,
            "nonzero_pixels": 0,
            "total_pixels": 0,
            "normalized_mean": 0.0,
        }
    nonzero = total - hist[0]
    max_abs = 0
    for idx in range(255, -1, -1):
        if hist[idx]:
            max_abs = idx
            break
    mean_abs = sum(idx * count for idx, count in enumerate(hist)) / float(total)
    return {
        "mean_abs": mean_abs,
        "max_abs": max_abs,
        "nonzero_pixels": nonzero,
        "total_pixels": total,
        "normalized_mean": mean_abs / 255.0,
    }


def _resolve_output_path(output_path):
    if output_path:
        return output_path
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    logs_dir = os.path.join(repo_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(logs_dir, f"diff_{stamp}.png")


def main():
    parser = argparse.ArgumentParser(description="Compute a visual diff between two images.")
    parser.add_argument("--before", required=True, help="Path to the baseline image")
    parser.add_argument("--after", required=True, help="Path to the new image")
    parser.add_argument("--output", default=None, help="Output diff image path (defaults to logs/)")
    parser.add_argument("--scale", type=float, default=4.0, help="Brightness scale for diff visibility")
    args = parser.parse_args()

    try:
        before = _load_image(args.before)
        after = _load_image(args.after)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Failed to load images: {exc}"}))
        raise SystemExit(1)

    if before.size != after.size:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Image sizes differ: {before.size} vs {after.size}",
                }
            )
        )
        raise SystemExit(1)

    diff = ImageChops.difference(before, after)
    stats = _diff_stats(diff)

    diff_out = diff
    if args.scale and args.scale != 1.0:
        try:
            diff_out = ImageEnhance.Brightness(diff_out).enhance(args.scale)
        except Exception:
            diff_out = diff

    output_path = _resolve_output_path(args.output)
    try:
        diff_out.save(output_path)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Failed to save diff: {exc}"}))
        raise SystemExit(1)

    result = {
        "ok": True,
        "error": None,
        "data": {
            "before": args.before,
            "after": args.after,
            "diff_path": output_path,
            "stats": stats,
        },
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
