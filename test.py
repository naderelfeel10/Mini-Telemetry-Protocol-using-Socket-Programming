import subprocess
import time
import csv
import os
import matplotlib.pyplot as plt
import argparse



parser = argparse.ArgumentParser()

parser.add_argument(
    "--cmd",
    type=str,
    required=True,
    help="test type"
)



args = parser.parse_args()


cmd = args.cmd


repeats = 5
CLIENT_CMD = ["python3", "client.py", "--batch=2", "--device_id=101"]
SERVER_CMD = ["python3", "server.py"]



print(f"\n=== {cmd.upper()} TESTS ===")

for i in range(repeats):

    print(f"Run {i+1}/{repeats}")

    subprocess.run(["./test_netem.sh", cmd])

    server = subprocess.Popen(SERVER_CMD)
    time.sleep(1)

    client = subprocess.Popen(CLIENT_CMD)
    client.wait()

    time.sleep(1)

    server.terminate()
    server.wait()