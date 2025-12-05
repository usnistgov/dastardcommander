import os
import platform
import subprocess

TARGET = 64 * 1024 * 1024   # 64 MB


def get_rmem_max():
    """Return the current Linux rmem_max as an integer."""
    out = subprocess.check_output(
        ["sysctl", "-n", "net.core.rmem_max"],
        text=True
    )
    return int(out.strip())


def is_rmem_acceptable():
    return get_rmem_max>=TARGET

def instructions():
    return """LINUX INSTRUCTIONS:
    your rmem is too low, this will make dastard lose data for ABACO Sources
    do this (fix for this session):
       sudo sysctl -w net.core.rmem_max=67108864
    then add this to /etc/sysctl.conf (persistent fix across reboots):
        net.core.rmem_max=67108864
    """

def rmem_check_command_line_instructions():
    rmem_max = get_rmem_max()
    if rmem_max < TARGET:
        print(instructions())
    else:
        print(f"Abaco RMEM check complete, {rmem_max=} >= {TARGET=}")
    
