import socket
import struct
import time
import csv
import os

import threading

from collections import defaultdict, deque


# server setup
PORT = 5053
SERVER = socket.gethostbyname(socket.gethostname())
ADDR = (SERVER, PORT)
print("SERVER:", ADDR)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(ADDR)

log_file = "telemetry_log.csv"
metrics_file = "metrics_summary.csv"


print("Server started. Waiting for packets...\n")

device_state = {}


# packet format
HEADER_FORMAT = '!B H H I B 2x'   
PAYLOAD_FORMAT = '!f f I'      

HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
PAYLOAD_SIZE = struct.calcsize(PAYLOAD_FORMAT)

HEARTBEAT_TIMEOUT = 10 

last_heartbeat = {}


REORDER_WINDOW_SEC = 0.25  
reorder_buffers = defaultdict(list)  

lock = threading.Lock()


# Create CSV with header if not exists

if not os.path.exists(log_file):
    with open(log_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["device_id", "seq", "payload_ts", "arrival_time", "duplicate_flag", "gap_flag", "temp", "hum"])

if not os.path.exists(metrics_file):
    with open(metrics_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["bytes_per_report", "packets_received", "duplicate_rate", "sequence_gap_count", "cpu_ms_per_report"])



def flush_reorder_buffers():
    """
    Periodically flush entries older than REORDER_WINDOW_SEC in timestamp order to CSV.
    """
    while True:
        now = time.time()
        with lock:
            for dev, buf in list(reorder_buffers.items()):
                ready = [item for item in buf if now - item[1] >= REORDER_WINDOW_SEC]  # item[1] is arrival_time
                if ready:
                    # sort by payload timestamp (item[0])
                    ready.sort(key=lambda x: x[0])

                    with open(log_file, 'a', newline='') as f:
                        writer = csv.writer(f)
                        for (payload_ts, arrival_time, seq, duplicate_flag, gap_flag, temp, hum) in ready:
                            writer.writerow([dev, seq, int(payload_ts), arrival_time, duplicate_flag, gap_flag, temp, hum])
                    # remove flushed items from buffer
                    reorder_buffers[dev] = [item for item in buf if now - item[1] < REORDER_WINDOW_SEC]
        time.sleep(0.05)

threading.Thread(target=flush_reorder_buffers, daemon=True).start()



def monitor_heartbeats():
    while True:
        current_time = time.time()
        for dev, last_time in last_heartbeat.items():
            if current_time - last_time > HEARTBEAT_TIMEOUT:
                print(f"[WARN] Device {dev} might be offline! Last heartbeat {current_time - last_time:.1f}s ago")
        time.sleep(1) 

threading.Thread(target=monitor_heartbeats, daemon=True).start()


def flush_all_reorder_buffers():
    with lock:
        for dev, buf in reorder_buffers.items():
            if buf:
                buf.sort(key=lambda x: x[0]) 
                with open(log_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    for (payload_ts, arrival_time, seq, dup, gap, temp, hum) in buf:
                        writer.writerow([dev, seq, int(payload_ts), arrival_time, dup, gap, temp, hum])
                reorder_buffers[dev] = []


# Metrics to Collect
total_bytes = 0
packets_received = 0
duplicate_count = 0
sequence_gap_count = 0
cpu_time = 0.0
total_readings = 0


while(1):
    try:    
        start_cpu = time.process_time()

        data, addr = sock.recvfrom(2000)

        end_cpu = time.process_time()

        cpu_time += (end_cpu - start_cpu)

        if len(data) < HEADER_SIZE:
            print("[WARN] Packet too short!")
            continue

        msg_type, device_id, seq_num, timestamp, batch_count = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])

        packets_received += 1
        total_readings += batch_count
        total_bytes += len(data)
        arrival_time = time.time()


        print(f"\n>> Packet received from {addr}")
        print(f"   TYPE={msg_type}, Dev={device_id}, Seq={seq_num}, Batch={batch_count}")



        # Parse all readings inside batch
        readings = []

        offset = HEADER_SIZE

        for i in range(batch_count):
            if offset + PAYLOAD_SIZE > len(data):
                print("[WARN] Payload out of range")
                break

            temp, hum, ts = struct.unpack(PAYLOAD_FORMAT, data[offset:offset + PAYLOAD_SIZE])
            offset += PAYLOAD_SIZE

            readings.append((temp, hum, ts))
            print(f"   Reading {i+1}: Temp={temp}C  Hum={hum}%  TS={ts}")


        if msg_type == 0:
            print(f"[INIT] Device {device_id} registered")

            device_state[device_id] = {'last_seq': seq_num}
            continue

        if msg_type == 2:

            print(f"[HEARTBEAT] Device {device_id} alive, seq={seq_num}")
            #last_heartbeat = {device_id: time.time()}

            last_heartbeat[device_id] = time.time()
            device_state[device_id]['last_seq'] = seq_num

            with open(log_file, 'a', newline='') as f:
                writer = csv.writer(f)

                # device_id, seq, timestamp, arrival_time, duplicate_flag, gap_flag
                writer.writerow([device_id, seq_num, ts, arrival_time])

            continue


        if msg_type == 1:

            duplicate_flag = 0
            gap_flag = 0
            '''
            if device_id in device_state:
                last_seq = device_state[device_id]['last_seq']


                if seq_num <= last_seq:
                    duplicate_flag = 1


                elif seq_num > last_seq + 1:
                    if batch_count == 1:    
                        gap_flag = 1
                else:

                    gap_flag = 0       

            device_state[device_id] = {'last_seq': seq_num}
            '''
            # send ack msg back to the client
            ack_packet = struct.pack('!B H H', 3, device_id, seq_num)
            sock.sendto(ack_packet, addr)

            if device_id in device_state:
                last_seq = device_state[device_id]['last_seq']
                if seq_num <= last_seq:
                    duplicate_flag = 1
                    duplicate_count += 1

                elif seq_num - last_seq > 1:
                    #if batch_count == 1:
                    gap_flag = 1
                    sequence_gap_count += (seq_num - last_seq - 1)


            if duplicate_flag == 0:
                device_state[device_id]['last_seq'] = seq_num

            #for (temp, hum, payload_ts) in readings:
            #        reorder_buffers[device_id].append((payload_ts, arrival_time, seq_num, duplicate_flag, gap_flag, temp, hum))

            
            with lock:
                for (temp, hum, payload_ts) in readings:
                    reorder_buffers[device_id].append(
                        (payload_ts,
                         arrival_time,
                         seq_num,
                         duplicate_flag,
                         gap_flag,
                         round(temp, 2),
                         round(hum, 2))
                    )
            print(f"[DATA] Dev={device_id} Seq={seq_num} | Dup={duplicate_flag} Gap={gap_flag}")
            continue        


        if msg_type == 4:
            
            print(f"\n[END] Device {device_id} finished test")

            flush_all_reorder_buffers()
            # calculate final metrics

            bytes_per_report = total_bytes / total_readings if total_readings else 0
            duplicate_rate = duplicate_count / packets_received if packets_received else 0
            cpu_ms_per_report = (cpu_time / total_readings * 1000) if total_readings else 0

            print("\n=== FINAL METRICS SUMMARY ===")
            print(f"bytes_per_report: {bytes_per_report:.2f}")
            print(f"packets_received: {packets_received}")
            print(f"duplicate_rate: {duplicate_rate:.3f}")
            print(f"sequence_gap_count: {sequence_gap_count}")
            print(f"cpu_ms_per_report: {cpu_ms_per_report:.3f}")

            with open(metrics_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    bytes_per_report,
                    packets_received,
                    duplicate_rate,
                    sequence_gap_count,
                    cpu_ms_per_report
                ])

            del device_state[device_id]
            break


        else:

            print("[WARN] Unknown message type")



    except socket.timeout:
        continue
    except Exception as e:
        print("[ERROR]", e)
        continue 




