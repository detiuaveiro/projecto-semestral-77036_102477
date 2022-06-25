import fcntl
import logging
import os
import pickle
import selectors
import socket
import sys
import time
import argparse


class Client:
    def __init__(self, address):
        """
            Parameters:
                address: Adress of the node in the Network this CLient is connecting to
        """
        self.dht_addr = address
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.logger = logging.getLogger("NetworkClient")
        self.m_selector = selectors.DefaultSelector()
        self.m_selector.register(sys.stdin, selectors.EVENT_READ, self.got_keyboard_data)

    def got_keyboard_data(self, stdin):
        """
            Reads user input from the terminal.
            Accepts four commands:
                /help -> Lists the available commands
                /list -> Will fetch the list of the images stored by the Network
                /image -> Will fetch an image by Name
                /exit -> Terminates the Client
        """
        keyboard_input = stdin.read()
        parameters = keyboard_input.rstrip().split()

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
            print('''\n/list -> Will fetch the list of the images stored by the Network
/image [Name] -> Will fetch an image by Name
/exit -> Terminates the Client\n''')

    def get_list(self):
        """
            Processes a /list request.
            Returns the list of images stored by the contacted Network, using a REQUEST_LIST message
        """
        msg = {"method": "REQUEST_LIST"}

        # Send the Message
        pickled_message = pickle.dumps(msg)
        self.socket.sendto(len(pickled_message).to_bytes(8, 'big'), self.dht_addr)
        self.socket.sendto(pickled_message, self.dht_addr)

        # Receive the Reply
        data, addr = self.socket.recvfrom(8)
        msg_size = int.from_bytes(data, "big")
        pickled_message, addr = self.socket.recvfrom(msg_size)
        out = pickle.loads(pickled_message)
        if out["method"] != "REPLY_LIST":
            self.logger.error("Invalid msg: %s", out)
            return None

        print("List of images:")
        for image in out["request"]:
            print("> " + image)

        return out["request"]

    def get_image(self, name):
        """
            Processes a /image request.
            Returns the image, if stored by the contacted Network, using a REQUEST_IMG message
            Parameters:
                name: Name of the Image to be fetched
        """
        msg = {"method": "REQUEST_IMG", "request": name}

        # Send the Message
        pickled_message = pickle.dumps(msg)
        self.socket.sendto(len(pickled_message).to_bytes(8, 'big'), self.dht_addr)
        self.socket.sendto(pickled_message, self.dht_addr)

        # Receive the Reply
        data, addr = self.socket.recvfrom(8)
        msg_size = int.from_bytes(data, "big")

        print("Loading image, please wait!")

        size = 0
        msg_bytes = bytes("".encode('UTF-8'))
        start = time.time()
        while size < msg_size:
            update = time.time() - start
            if (update > 7):
                break

            try:
                data, addr = self.socket.recvfrom(4096)
            except socket.timeout:
                print("Socket timeout")
                return 0

            if len(data) == 0:
                return 0

            msg_bytes += data
            size += 4096

        try:
            out = pickle.loads(msg_bytes)
            img = out["request"]
            img.show()
            return img
        except:
            print("There was a problem, try asking again!")
            return 0

    def loop(self):
        """Loop indefinitely."""
        orig_fl = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, orig_fl | os.O_NONBLOCK)

        while True:
            sys.stdout.write('Type something and hit enter: ')
            sys.stdout.flush()
            for k, _ in self.m_selector.select():
                callback = k.data
                callback(k.fileobj)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("node_addr", type=str, help="Address of the node to be contacted")
    parser.add_argument("node_port", type=int, help="Port of the node to be contacted")
    args = parser.parse_args()

    client = Client((args.node_addr, args.node_port))
    client.loop()
