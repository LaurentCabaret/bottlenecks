#!/usr/bin/env python3

# Copyright 2022 Vincent Jacques

import dataclasses
import json
import logging
import os
import subprocess
import sys
import textwrap
import time

import click


logging.basicConfig(level=logging.INFO)


@click.group()
def main():
    pass


@main.command(help=textwrap.dedent("""\
    Find the value of the positive integer argument to pass to PROGRAM so that its duration is TARGET_DURATION.
    PROGRAM is called repeatedly with different arguments.
    The value that makes it last for about TARGET_DURATION seconds is then printed on the standard output.
"""))
@click.argument("program")
@click.option("--target-duration", show_default=True, default=10, metavar="TARGET_DURATION", help="The target duration, in seconds")
@click.option("--tolerance", show_default=True, default=0.05, metavar="TOLERANCE", help="Stop when duration is within TOLERANCE percents of TARGET_DURATION")
def calibrate(program, target_duration, tolerance):
    size = 0.5
    duration = 0
    while duration < target_duration:
        lo_size = size
        size *= 2
        duration = run_monitored([program, str(int(size))], 1).clock_duration_s
    hi_size = size
    while abs(duration - target_duration) / target_duration > tolerance:
        size = (lo_size + hi_size) / 2
        duration = run_monitored([program, str(int(size))], 1).clock_duration_s
        if duration > target_duration:
            hi_size = size
        else:
            lo_size = size
    logging.info(f"Duration reached: {duration}s, relative error: {abs(duration - target_duration) / target_duration}")
    print(int(size))


@main.command()
@click.argument("program")
@click.argument("size")
@click.option("--min-parallelism", default=1)
@click.option("--max-parallelism", default=16)
def run(program, size, min_parallelism, max_parallelism):
    durations = {}
    for parallelism in range(min_parallelism, max_parallelism + 1):
        durations[parallelism] = run_monitored([program, size], parallelism).clock_duration_s
    json.dump(durations, sys.stdout)


def run_monitored(command, parallelism):
    logging.debug(f"Running {command} with {parallelism} threads")
    time_before = time.perf_counter()
    subprocess.run(
        command,
        env=dict(os.environ, OMP_NUM_THREADS=str(parallelism)),
        check=True,
    )
    time_after = time.perf_counter()
    clock_duration_s = time_after - time_before
    logging.info(f"Running {command} with {parallelism} threads took {clock_duration_s:.2f}s")
    return MonitoredRunResult(
        clock_duration_s=clock_duration_s,
    )


@dataclasses.dataclass
class MonitoredRunResult:
    clock_duration_s: float


@main.command()
@click.argument("file-names", nargs=-1)
def report(file_names):
    import matplotlib.pyplot as plt  # Don't import at top-level because:
    # - it's quite long
    # - it calls a subprocess during initialization, which polutes resource.getrusage

    data = {}
    for file_name in file_names:
        assert file_name.endswith(".json")
        with open(file_name) as f:
            data[os.path.basename(file_name)[:-5]] = {int(k): v for  k, v in json.load(f).items()}

    parallelisms = sorted(set(k for d in data.values() for k in d.keys()))

    fig, ax = plt.subplots(figsize=(8, 6), layout="constrained")

    for n in range(10):
        p = (n + 1) / 10
        ax.plot(
            parallelisms,
            [1 - p + p / parallelism for parallelism in parallelisms],
            "--",
            linewidth=0.5,
            color="grey",
        )

    for name, durations in data.items():
        ax.plot(
            parallelisms,
            [durations[parallelism] / durations[min(parallelisms)] for parallelism in parallelisms],
            "-o",
            label=name,
        )

    ax.set_xlabel("Parallelism")
    ax.set_ylabel("Duration (s)")
    ax.set_xlim(left=1, right=max(parallelisms))
    ax.set_ylim(bottom=0, top=1)
    # ax.set_y
    ax.legend()
    fig.savefig("build/duration-vs-parallelism.png", dpi=300)


if __name__ == "__main__":
    main()