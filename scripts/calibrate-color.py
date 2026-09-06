#!/usr/bin/env python
"""Calibrate a dsh pet screenshot to the EAC native reference color balance.

Usage:
    py -3 scripts/calibrate-color.py <source.png> <reference.png> <output.png>
"""
import sys
from pathlib import Path

from PIL import Image, ImageStat


def channel_coeffs(src_stat, ref_stat):
    coeffs = []
    for index in range(3):
        src_mean = src_stat.mean[index]
        src_std = src_stat.stddev[index]
        ref_mean = ref_stat.mean[index]
        ref_std = ref_stat.stddev[index]
        gain = ref_std / src_std if src_std else 1.0
        offset = ref_mean - gain * src_mean
        coeffs.append((gain, offset))
    return coeffs


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    src = Image.open(argv[1]).convert("RGB")
    ref = Image.open(argv[2]).convert("RGB")
    src_stat = ImageStat.Stat(src)
    ref_stat = ImageStat.Stat(ref)
    coeffs = channel_coeffs(src_stat, ref_stat)

    channels = list(src.split())
    for index, (gain, offset) in enumerate(coeffs):
        channels[index] = channels[index].point(
            lambda value, gain=gain, offset=offset: max(0, min(255, round(gain * value + offset)))
        )
    out = Image.merge("RGB", channels)
    out.save(argv[3], "PNG")

    print("source mean/std:", tuple(round(v, 2) for v in src_stat.mean), tuple(round(v, 2) for v in src_stat.stddev))
    print("reference mean/std:", tuple(round(v, 2) for v in ref_stat.mean), tuple(round(v, 2) for v in ref_stat.stddev))
    print("channel params (gain, offset):", [(round(g, 4), round(o, 2)) for g, o in coeffs])
    print("saved:", argv[3])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
