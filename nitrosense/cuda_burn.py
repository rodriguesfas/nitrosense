"""VRAM / light GPU occupancy via libcuda (no torch)."""

from __future__ import annotations

import argparse
import time
from ctypes import CDLL, POINTER, byref, c_int, c_size_t, c_void_p


def _cuda() -> CDLL:
    lib = CDLL("libcuda.so.1")
    lib.cuInit.argtypes = [c_int]
    lib.cuDeviceGetCount.argtypes = [POINTER(c_int)]
    lib.cuCtxCreate_v2.argtypes = [POINTER(c_void_p), c_int, c_int]
    lib.cuMemAlloc_v2.argtypes = [POINTER(c_void_p), c_size_t]
    lib.cuMemFree_v2.argtypes = [c_void_p]
    lib.cuCtxDestroy_v2.argtypes = [c_void_p]
    lib.cuMemGetInfo_v2.argtypes = [POINTER(c_size_t), POINTER(c_size_t)]
    return lib


def run(duration_s: int, *, fraction: float = 0.65) -> int:
    duration_s = max(5, int(duration_s))
    fraction = max(0.1, min(0.85, float(fraction)))
    cuda = _cuda()
    if cuda.cuInit(0) != 0:
        print("cuInit failed", flush=True)
        return 1
    n = c_int()
    if cuda.cuDeviceGetCount(byref(n)) != 0 or n.value < 1:
        print("no CUDA device", flush=True)
        return 1
    ctx = c_void_p()
    if cuda.cuCtxCreate_v2(byref(ctx), 0, 0) != 0:
        print("cuCtxCreate failed", flush=True)
        return 1
    free = c_size_t()
    total = c_size_t()
    if cuda.cuMemGetInfo_v2(byref(free), byref(total)) != 0:
        cuda.cuCtxDestroy_v2(ctx)
        print("cuMemGetInfo failed", flush=True)
        return 1
    want = int(free.value * fraction)
    # Cap leave ~512 MiB headroom for the desktop.
    headroom = 512 * 1024 * 1024
    want = max(64 * 1024 * 1024, min(want, max(0, free.value - headroom)))
    ptr = c_void_p()
    if cuda.cuMemAlloc_v2(byref(ptr), want) != 0:
        cuda.cuCtxDestroy_v2(ctx)
        print(f"cuMemAlloc failed for {want} bytes", flush=True)
        return 1
    print(f"allocated_mib={want // (1024 * 1024)} free_mib={free.value // (1024 * 1024)}", flush=True)
    end = time.time() + duration_s
    # Touch allocation with free/realloc cycles to keep the GPU active without a custom kernel.
    try:
        while time.time() < end:
            time.sleep(0.25)
            f2 = c_size_t()
            t2 = c_size_t()
            cuda.cuMemGetInfo_v2(byref(f2), byref(t2))
    finally:
        cuda.cuMemFree_v2(ptr)
        cuda.cuCtxDestroy_v2(ctx)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--fraction", type=float, default=0.65)
    args = parser.parse_args()
    return run(args.duration, fraction=args.fraction)


if __name__ == "__main__":
    raise SystemExit(main())
