import fcntl
import logging
import os
import pickle
import selectors
import socket
import sys
from PIL import Image


class Client:
    def __init__(self, address):
        self.dht_addr = address
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.logger = logging.getLogger("DHTClient")
        self.m_selector = selectors.DefaultSelector()
        self.m_selector.register(sys.stdin, selectors.EVENT_READ, self.got_keyboard_data)

    def got_keyboard_data(self, stdin):
        keyboardInput = stdin.read()
        parameters = keyboardInput.rstrip().split()

        if parameters[0] == "/list":
            self.get_list()
        elif parameters[0] == "/image":
            if len(parameters) > 2:
                print("Erro: Só podes pedir uma imagem de cada vez\n")
            else:
                self.get_image(parameters[1])
        elif parameters[0] == "/exit":
            print("Closing connection...")
            logging.debug("Closing connection...")
            self.m_selector.unregister(sys.stdin)
            self.socket.close()
            quit()
        else:
            pass

    def get_list(self):
        msg = {"method": "REQUEST_LIST"}

        # Send the Message
        pickled_message = pickle.dumps(msg)
        self.socket.sendto(len(pickled_message).to_bytes(8, 'big'), self.dht_addr)
        self.socket.sendto(pickled_message, self.dht_addr)

        # Receive the Reply
        data, addr = self.socket.recvfrom(8)
        msgSize = int.from_bytes(data, "big")
        pickled_message, addr = self.socket.recvfrom(msgSize)
        out = pickle.loads(pickled_message)
        if out["method"] != "REPLY_LIST":
            self.logger.error("Invalid msg: %s", out)
            return None
        return print(out["request"])

    def get_image(self, hash):
        msg = {"method": "REQUEST_IMG", "request": hash}

        # Send the Message
        pickled_message = pickle.dumps(msg)
        self.socket.sendto(len(pickled_message).to_bytes(8, 'big'), self.dht_addr)
        self.socket.sendto(pickled_message, self.dht_addr)

        # Receive the Reply
        data, addr = self.socket.recvfrom(8)
        msgSize = int.from_bytes(data, "big")
        pickled_message, addr = self.socket.recvfrom(msgSize)
        out = pickle.loads(pickled_message)
        if out["method"] != "REPLY_IMG":
            self.logger.error("Invalid msg: %s", out)
            return None
        img = Image.frombytes("RGB", out["size"], out["request"])
        img.show()
        return img

    def loop(self):
        """Loop indefinitely."""
        # set sys.stdin non-blocking
        orig_fl = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, orig_fl | os.O_NONBLOCK)

        while True:
            sys.stdout.write('Type something and hit enter: ')
            sys.stdout.flush()
            for k, _ in self.m_selector.select():
                callback = k.data
                callback(k.fileobj)


if __name__ == "__main__":
    client = Client(("localhost", 5000))
    client.loop()

