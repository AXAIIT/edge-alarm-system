#!/usr/bin/python3
"""Apply the validated Project 08 Jetson CPU/GPU production clock profile."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess

CPU = Path('/sys/devices/system/cpu/cpufreq/policy0')
GPU = Path('/sys/class/devfreq/17000000.gv11b')
STATE = Path('/run/p08-jetson-clock-policy.json')
LOCK = Path('/run/lock/p08-vlm-clock-window')
CONFIG = Path('/etc/project08/jetson-clock-policy.json')
LIMITS = {'cpu_min_khz': CPU / 'scaling_min_freq', 'cpu_max_khz': CPU / 'scaling_max_freq',
          'gpu_min_hz': GPU / 'min_freq', 'gpu_max_hz': GPU / 'max_freq'}


def bounds():
    return {name: int(path.read_text().strip()) for name, path in LIMITS.items()}


def minimum(values):
    return {key: values[key] for key in ('cpu_min_khz', 'gpu_min_hz')}


def set_minimum(target):
    for key, hz in minimum(target).items():
        LIMITS[key].write_text(str(hz) + '\n')


def apply():
    power = subprocess.check_output(['nvpmodel', '-q'], text=True, stderr=subprocess.STDOUT).splitlines()
    if power[:2] != ['NV Power Mode: MODE_20W_6CORE', '8']:
        raise RuntimeError('Project 08 clock profile requires MODE_20W_6CORE ID 8')
    profile = json.loads(CONFIG.read_text(encoding='utf-8'))
    assert profile['profile_id'] == 'p08_jetson_20w_cpu_gpu_peak_v1'
    target = profile['production_bounds']
    initial = bounds()
    assert target == {'cpu_min_khz': 1420800, 'cpu_max_khz': 1420800,
                      'gpu_min_hz': 1109250000, 'gpu_max_hz': 1109250000}
    if STATE.exists():
        assert initial == target, 'existing clock policy is incomplete'
        return
    assert initial == profile['previous_dynamic_bounds'], initial
    assert (CPU / 'related_cpus').read_text().split() == [str(n) for n in range(6)]
    with STATE.open('x', encoding='utf-8') as f:
        json.dump(initial, f)
        f.write('\n')
    try:
        set_minimum(target)
        assert bounds() == target
    except BaseException:
        set_minimum(initial)
        assert bounds() == initial
        STATE.unlink()
        raise
    print(json.dumps(dict(profile=profile['profile_id'],before=initial,after=bounds())))


def restore():
    if not STATE.exists():
        return
    initial = json.loads(STATE.read_text(encoding='utf-8'))
    set_minimum(initial)
    assert bounds() == initial
    STATE.unlink()
    print(json.dumps(dict(restored=bounds())))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=('apply','restore'))
    action = p.parse_args().action
    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (apply if action == 'apply' else restore)()


if __name__ == '__main__':
    main()
