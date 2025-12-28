import socket
import struct
import time
import random

import threading
import argparse


# get batch and device id from user
parser = argparse.ArgumentParser(description="Client batch sender")

parser.add_argument(
    "--batch",
    type=int,
    required=True,
    help="Number of messages in batch"
)

parser.add_argument(
    "--device_id",
    type=int,
    required=True,
    help="Device ID"
)

parser.add_argument("--interval", type=int, default=2,
                    help="Reporting interval in seconds")


args = parser.parse_args()


MAX_READINGS_PER_PACKET = args.batch
device_id = args.device_id
REPORTING_INTERVAL = args.interval


#print("Batch count:", batch_count)
#print("Device ID:", device_id)



# connection setup

#same as the open port 
PORT = 5053
HOST = socket.gethostbyname(socket.gethostname()) 
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)



# packet format adn construction : 

#header format is : 
# 1, 2 , 2 , 4 , 1 , 2 
# msg_type, device_id, seq, timestamp, batch_count , padding 

HEADER_FORMAT = '!B H H I B 2x'

class Header:
    def __init__(self, msg_type, device_id, seq, timestamp):
        self.msg_type = msg_type     
        self.device_id = device_id     
        self.seq = seq                
        self.timestamp = timestamp     


# 4 , 4 , 4
# tmp , hum , timestamp
PAYLOAD_FORMAT = '!f f I'
class Payload:
    SIZE = struct.calcsize(PAYLOAD_FORMAT)

    def __init__(self, temp, hum):
        self.temp = float(temp)
        self.hum = float(hum)




# sending first packet from the device : 

seq = 1
msg_type =0
timestamp = int(time.time())


# construct header : 
init_header = Header(msg_type, device_id, seq, timestamp)
packet_header = struct.pack(HEADER_FORMAT, init_header.msg_type, init_header.device_id, init_header.seq, init_header.timestamp, 1)

#print(struct.calcsize(HEADER_FORMAT))

#construct dummy payload payload
init_payload = Payload(0.0, 0.0)
packet_payload = struct.pack(PAYLOAD_FORMAT, init_payload.temp, init_payload.hum, timestamp)

packet = packet_header + packet_payload


# sending the packet
sock.sendto(packet, (HOST, PORT))
print("INIT message sent.")






msg_type = 1 


batch = []

# creating a whole different thread just to send heartbeat packets:

HEARTBEAT_INTERVAL = 5
last_heartbeat = time.time()

HeartBeatMSGType = 2
def heartbeat_thread():
    #heart_beat_seq = 0
    global seq

    while True:
        #heart_beat_seq += 1
        seq+=1
        timestamp = int(time.time())
        header = struct.pack(HEADER_FORMAT, HeartBeatMSGType, device_id, seq, timestamp, 1)
        payload = struct.pack(PAYLOAD_FORMAT, 0.0, 0.0, timestamp)

        packet = header + payload

        sock.sendto(packet, (HOST, PORT))
        print(f"Sent HEARTBEAT #{seq}")
        time.sleep(HEARTBEAT_INTERVAL)

hb_thread = threading.Thread(target=heartbeat_thread, daemon=True)
hb_thread.start()



# constructing retransimition thread for critical packets :

unacked_packets = {}
TIMEOUT = 2
def retransmit_loop():
    while True:
        now = time.time()
        for seq_num, (packet, ts) in list(unacked_packets.items()):
            if now - ts > TIMEOUT:
                print(f"[RETRANSMIT] Seq {seq_num}")
                sock.sendto(packet, (HOST, PORT))
                unacked_packets[seq_num] = (packet, time.time())
        time.sleep(0.5)

retransmit_thread  =  threading.Thread(target=retransmit_loop, daemon=True)
retransmit_thread.start()




TEST_DURATION = 60
start_time = time.time()

while time.time() - start_time < TEST_DURATION:
        
    current_time = time.time()
    '''
    if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:

        seq += 1

        #if seq > 5:
        #    time.sleep(11)
        
        timestamp = int(time.time())
        header = struct.pack(HEADER_FORMAT, 2, device_id, seq, timestamp,1)
        
        payload = struct.pack(PAYLOAD_FORMAT, 0.0, 0.0, timestamp)
        
        sock.sendto(header + payload, (HOST, PORT))
        
        print(f"Sent HEARTBEAT #{seq}")
        last_heartbeat = current_time
        continue
    '''


    #seq += 1
    timestamp = int(time.time())
    temp = round(random.uniform(20, 35), 2)
    hum = round(random.uniform(40, 70), 2)

    #header = Header(msg_type, device_id, seq, timestamp)
    #packet_header = struct.pack(HEADER_FORMAT, header.msg_type, header.device_id, header.seq, header.timestamp)

    #print(struct.calcsize(HEADER_FORMAT))

    #payload = Payload(temp, hum)
    #packet_payload = struct.pack(payload.FORMAT, payload.temp, payload.hum)

    #packet = packet_header + packet_payload

    
    batch.append((temp, hum, timestamp))

    #print(header.seq , " || ", header.timestamp)
    
    if len(batch) == MAX_READINGS_PER_PACKET:
        seq += 1
        msg_type = 1 
        batch_count = len(batch)
        timestamp = int(time.time())

        header = struct.pack("!B H H I B 2x",
                             msg_type,
                             device_id,
                             seq,
                             timestamp,
                             batch_count)
        

        payload = b""

        for (t, h, ts) in batch:
            payload += struct.pack("!f f I", t, h, ts)

        packet = header + payload

        sock.sendto(packet, (HOST, PORT))
        
        # after sending the packet to the server , add it to the unpacked packet , so we can check if we need to retransmit
        unacked_packets[seq] = (packet, timestamp)
        print(f"Sent BATCH #{seq} with {batch_count} readings!")
        batch = []   

       # waiting for ack msg from the server : 


        try : 
            #print("in loop")
            sock.settimeout(0.5)
            ack_data , _ = sock.recvfrom(1024)

            #sock.sendto(packet, (HOST, PORT))

            ack_type, ack_dev, ack_seq = struct.unpack('!B H H', ack_data)
            if ack_seq in unacked_packets:
                
                print(f"[ACK] Seq {ack_seq} received")
                # remove from unpacked packets so we don't retransmit it 
                del unacked_packets[ack_seq]

        except socket.timeout:
                pass


    time.sleep(REPORTING_INTERVAL)


END_MSG_TYPE = 4
timestamp = int(time.time())

end_header = struct.pack(
    HEADER_FORMAT,
    END_MSG_TYPE,
    device_id,
    seq + 1,
    timestamp,
    0
)

sock.sendto(end_header, (HOST, PORT))
print("[CLIENT] END message sent to server")



