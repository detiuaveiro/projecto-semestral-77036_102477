from PIL import Image
import imagehash
import logging
import pickle
import socket
import threading
from time import time, sleep
import argparse
import os

# Status of the peers in the Routing Table
ALIVE = 1
CHECKING = 2
SUS = 3
DEAD = 4

class DHTNode(threading.Thread):
    """ DHT Node Agent. """

    def __init__(self, address, folder, id, dht_address=None, timeout=15):
        """Constructor

        Parameters:
            address: self's address
            id: self's ID
            dht_address: address of a node in the Network
            timeout: impacts how often stabilize algorithm is carried out
        """
        threading.Thread.__init__(self)
        print("Node " + str(id) + ": " + str(address))
        self.done = False

        self.identification = id
        self.addr = address  # My address
        self.dht_address = dht_address  # Address of the initial Node
        self.image_directory = "./" + folder    # Directory where my photos are stashed
        self.keepalive_time = 30

        self.routingTable = {}  # Dict that will keep the addresses of the other nodes in the mesh {id:[address]}
        self.routingTableStatus = {}  # Dict that will keep the connection status of the other nodes in the mesh {
        # id:(Status,Time)}, Status can be 1 (ALIVE), 2 (CHECKING), 3(SUSPECT), 4(DEAD)

        self.keystore = {}  # Where all data is stored {id: [name,...]}
        self.backupLocations = {}  # Lists the peers which are storing backups of the images belonging to me {id: img_name}

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(timeout)
        self.logger = logging.getLogger("Node {}".format(self.identification))

        if dht_address is None:
            self.inside_dht = True
            self.keystore[self.identification] = self.get_images()
        else:
            self.inside_dht = False

    # FUNCTIONS TO SEND AND RECEIVE MESSAGES IN THE SOCKET
    def send(self, address, msg):
        """ Send msg to address. """
        payload = pickle.dumps(msg)

        # send message size
        msg_size = len(payload)
        self.socket.sendto(msg_size.to_bytes(8, 'big'), address)

        # if the image is too big it will divide it in parts and send them
        # note that we are assuming that the messages will arrive in order
        size = 0
        if msg_size > 4096:
            while size < msg_size:
                self.socket.sendto(payload[size: 4096 + (size + 1)], address)
                size += 4096
                sleep(0.001)
        else:
            self.socket.sendto(payload, address)

    def recv(self):
        """ Retrieve msg payload and from address."""
        try:
            data, addr = self.socket.recvfrom(8)
            msgSize = int.from_bytes(data, "big")

            if not data:
                return None, None

            # if the receiving message is too big it will divide and receive it in parts
            # note that we are assuming that the messages will arrive in order
            if msgSize > 4096:
                size = 0
                payload = bytes("".encode('UTF-8'))
                while size < msgSize:
                    data, addr = self.socket.recvfrom(4096)

                    payload += data
                    size += 4096
            else:
                payload, addr = self.socket.recvfrom(msgSize)

        except socket.timeout:
            return None, None

        if len(payload) == 0:
            return None, addr

        return payload, addr

    # FUNCTIONS INVOLVED IN THE STABILIZATION PROTOCOL
    def stabilize(self):
        """
            Outlines the steps of the Stabilization protocol.
        """
        self.check_alive()
        self.stay_alive()

    def stay_alive(self):
        """
        Part of the Stabilization protocol.
        Sends an ALIVE message to all the nodes in the Routing Table if their last contact with us was longer than the
        KEEPALIVE time, to check if they're still active.
        Afterwards, it sets the status of all contacted nodes to CHECKING. The status will be reset to ALIVE if they
        reply with an ALIVE_ACK message.
        """
        for node, addr in self.routingTable.items():
            if time() - self.routingTableStatus[node][1] > self.keepalive_time:
                hello_msg = {
                    "method": "ALIVE",
                    "args": {"addr": self.addr, "id": self.identification},
                }
                self.send(addr, hello_msg)
                if self.routingTableStatus[node][0] == ALIVE:
                    self.routingTableStatus[node][0] = CHECKING
            else:
                self.routingTableStatus[node][0] = ALIVE
            sleep(1)

    def check_alive(self):
        """
            Part of the Stabilization protocol.
            Checks all the nodes in the routing table to see if they're still alive.
            In case they haven't replied to an ALIVE message, their status will turn to SUS.
            If they are still SUS after being contacted with an ALIVE message again, they will be considered DEAD.
            If our node was saving backup images of a DEAD node, they are restored to our main folder.
        """
        for node in list(self.routingTableStatus.keys()):
            if self.routingTableStatus[node][0] == CHECKING:
                self.routingTableStatus[node][0] = SUS
            elif self.routingTableStatus[node][0] == SUS:
                self.routingTableStatus[node][0] = DEAD
                if os.path.isdir(os.path.join(self.image_directory, "backup_node" + str(node))):
                    self.restoreBackups(node)
                del self.routingTable[node]


        self.logger.info(self)

    # FUNCTIONS THAT WILL FETCH IMAGES REQUESTED BY THE CLIENT
    def get(self, addr, output):
        """
            Processes REQUEST_IMG messages
            If this node stores the image, it will send it to the requesting addr.
            If it doesn't, it will forward the message to the node that stores it.
            Parameters:
                addr: addr of the node/client that sent the message
                output: content of the message
        """
        if output["request"] in [val[1] for val in self.keystore[self.identification]] and "args" not in output.keys():
            # self.logger.info(output["request"])
            self.send_image(addr, output["request"])
        elif "args" in output.keys():
            # self.logger.info(output["args"])
            self.send_image(output["args"], output["request"])
        else:
            self.send(self.routingTable[self.get_key(output["request"])],
                      {"method": "REQUEST_IMG", "args": addr, "request": output["request"]})

    def get_key(self, val):
        """
            Auxiliary function to get().
            Returns the addr of the node storing the image.
            Parameters:
                val: Name of the image to be sent
        """
        for key, value in self.keystore.items():
            if val in [val[1] for val in value]:
                return key

        return "key doesn't exist"

    def send_image(self, addr, name):
        """
            Sends a REPLY_IMG message containing the requested image.
            Parameters:
                addr: address where the image will be sent
                name: name of the image to be sent
        """
        img_path = self.image_directory + "/" + name
        image = Image.open(img_path)
        self.send(addr, {"method": "REPLY_IMG", "request": image})

    # FUNCTIONS INVOLVED IN THE BACK-UP PROTOCOL
    def check_backedup_images(self):
        """
            Traverses the list of images stored by this node, and checks if each one has been backed up by a peer or not.
            Returns the list of images of the node that haven't been backed up.
        """
        unbackedImages = []

        for img in self.keystore[self.identification]:
            if len(list(self.backupLocations.values())) != 0 and img not in [x for v in self.backupLocations.values() for x in v]:
                unbackedImages.append(img)
            elif len(self.backupLocations.values()) == 0:
                unbackedImages.append(img)


        if len(unbackedImages) > 0:
            return unbackedImages
        else:
            return None

    def set_backups(self, unbackedImages):
        """
            Assigns to each of the peers of this node a set of unbacked images, to be backed up by them.

            Parameters:
                unbackedImages: List of images belonging to the node that haven't yet been backed up
        """
        peers = len(self.routingTable.keys())
        images = len(unbackedImages)

        imagePerPeer = images // peers
        sentImageIdx = 0

        rt_keys = list(self.routingTable.keys())

        print("Starting Backup, please wait!")

        for i in range(peers - 1):
            self.send_backup(self.routingTable[rt_keys[i]],
                             unbackedImages[sentImageIdx:sentImageIdx + imagePerPeer])
            sentImageIdx += imagePerPeer
        self.send_backup(self.routingTable[rt_keys[-1]], unbackedImages[sentImageIdx:])
        sleep(0.01)

    def send_backup(self, addr, imageList):
        """
            Sends to a peer the list of images it has been assigned to back up.

            Parameters:
                addr: Address of the peer
                imageList: Images belonging to this node that the peer will back up
        """
        all_img = []
        all_img_info = []
        for imageInfo in imageList:
            img_path = self.image_directory + "/" + imageInfo[1]
            image = Image.open(img_path)
            all_img.append(image)
            all_img_info.append(imageInfo)

        for i in range(len(all_img)):
            backup_msg = {
                "method": "SEND_BACKUP",
                "id": self.identification,
                "request": all_img[i],
                "info": all_img_info[i],
            }
            self.send(addr, backup_msg)

    def receive_backup(self, addr, output):
        """
            Processes SEND_BACKUP message.
            Stores the images sent by a peer in its corresponding backup folder.
            Sends a BACKUP_ACK message to the peer informing that the image has been successfully backed-up.
            Parameters:
                addr: Address of the peer
                output: Content of the SEND_BACKUP message
        """
        # Verifiy if the back-up directory of the peer already exists
        if "backup_node" + str(output["id"]) not in os.listdir(self.image_directory):
            os.mkdir(os.path.join(self.image_directory, "backup_node" + str(output["id"])))

        # for i in range(len(output["request"])):
        image = output["request"]
        image.save(os.path.join(self.image_directory, "backup_node" + str(output["id"]) + "/" + output["info"][1]))

        backup_ack_msg = {
            "method": "BACKUP_ACK",
            "id": self.identification,
            "info": output["info"],
        }

        self.send(addr, backup_ack_msg)

    def restoreBackups(self, node):
        """
            Function called wheen a peer has been considered DEAD.
            It will move the images from the backup folder of that peer to our main folder.

            Parameters:
                node: Node that has died
        """
        backupPath = os.path.join(self.image_directory, "backup_node" + str(node))
        for image in os.listdir(backupPath):
            os.rename(os.path.join(backupPath, image), os.path.join(self.image_directory, image))

        os.rmdir(backupPath)
        print("Node " + str(node) + " died, backup restore made!")

    # OTHER FUNCTIONS
    def node_join(self, args):
        """ Process JOIN_REQ message.
        It accepts a node into the Network and processes a JOIN_REP message.
        Parameters:
            args (dict): addr and id of the node trying to join
        """

        self.logger.debug("Node join: %s", args)
        recAddr = args["addr"]
        identification = args["id"]
        rt_reply = {}

        for node, addr in self.routingTable.items():
            rt_reply[node] = addr

        self.routingTable[identification] = recAddr
        self.routingTableStatus[identification] = [ALIVE, time()]
        self.send(recAddr, {"method": "JOIN_REP", "args": {'addr': self.addr, 'id': self.identification},
                            "routingTable": rt_reply, "keystore": self.keystore})

        self.logger.info(self)

    def get_images(self):
        """
            Function used to determine the hashes of the images stored by this node.
            It will check the resulting hashes agains the hashes of the images stored by the network, and in case
            there's a match, the image will be considered a duplicate and removed.

            Returns the list of images that are processed and validated
        """
        nodeImages = []
        if len(list(self.keystore.values())) != 0:
            hashes = [img[0] for img in list(self.keystore.values())[0]]
        else:
            hashes = []

        for image in os.listdir(self.image_directory):
            path = self.image_directory + '/' + image
            img_hash = str(imagehash.dhash(Image.open(path), 4))

            if img_hash not in hashes:
                hashes.append(img_hash)
                nodeImages.append((img_hash, image))
            else:
                os.remove(path)

        return nodeImages

    # LIFE CYCLE OF THE NODE
    def run(self):
        self.socket.bind(self.addr)
        self.logger.info(self)

        # Loop until joining the Network
        while not self.inside_dht:
            join_msg = {
                "method": "JOIN_REQ",
                "args": {"addr": self.addr, "id": self.identification}
            }
            self.send(self.dht_address, join_msg)
            payload, addr = self.recv()
            if payload is not None:
                output = pickle.loads(payload)
                self.logger.debug("O: %s", output)
                if output["method"] == "JOIN_REP":
                    neighborRT = output["routingTable"]

                    # Node updates its Routing Table with the information received from the accepting peer
                    # Addition of the nodes belonging to the accepting peer's Routing Table
                    self.routingTable = {key: (value[0], value[1]) for key, value in neighborRT.items()}
                    self.routingTableStatus = {key: [ALIVE, time()] for key in neighborRT.keys()}
                    # Addition of the accepting peer
                    self.routingTable[output["args"]["id"]] = (output["args"]["addr"][0], output["args"]["addr"][1])
                    self.routingTableStatus[output["args"]["id"]] = [ALIVE, time()]
                    self.keystore = output["keystore"]

                    # Insert node values (photos hash) in shared data structure. Compare them with existing photos to
                    # see if they're repeated
                    self.keystore[self.identification] = self.get_images()

                    # Sending an HELLO message to each peer, containing the identification of the photos stored by our node
                    for addr in self.routingTable.values():
                        hello_msg = {
                            "method": "HELLO",
                            "args": {"addr": self.addr, "id": self.identification},
                            "keystore": self.keystore[self.identification]
                        }
                        self.send(addr, hello_msg)

                    # In case our node isn't the first one in the Network, it will backup its images to the peers
                    if not self.backupLocations and len(self.routingTable.keys()) >= 1:
                        self.set_backups(self.keystore[self.identification])

                    self.inside_dht = True
                    self.logger.info(self)

        while not self.done:
            self.logger.info(self)
            payload, addr = self.recv()
            if payload is not None:
                output = pickle.loads(payload)
                self.logger.info("%s: %s", self.identification, output)
                if output["method"] == "JOIN_REQ":
                    self.node_join(output["args"])
                elif output["method"] == "HELLO":
                    # Adding the node to the Routing Table
                    self.routingTable[output["args"]["id"]] = (output["args"]["addr"][0], output["args"]["addr"][1])
                    self.routingTableStatus[output["args"]["id"]] = [ALIVE, time()]
                    self.keystore[output["args"]["id"]] = output["keystore"]
                    self.logger.info(self)
                elif output["method"] == "ALIVE":
                    # Sends an ALIVE_ACK message notifying self is alive
                    ack_msg = {
                        "method": "ALIVE_ACK",
                        "args": {"addr": self.addr, "id": self.identification},
                    }
                    self.routingTableStatus[output["args"]["id"]] = [ALIVE, time()]
                    self.send(addr, ack_msg)
                elif output["method"] == "ALIVE_ACK":
                    # Changes the status of the sender to alive in the Routing Table
                    self.routingTableStatus[output["args"]["id"]] = [ALIVE, time()]
                elif output["method"] == "REQUEST_IMG":
                    # handles the request for an image
                    if "id" in output.keys():
                        self.routingTableStatus[output["id"]] = [ALIVE, time()]
                    self.get(addr, output)
                elif output["method"] == "REQUEST_LIST":
                    # handles the request for list of images stored in the Network
                    values = self.keystore.values()
                    list_values = []
                    for x in values:
                        list_values += [y[1] for y in x if y[1] not in list_values]
                    self.send(addr, {"method": "REPLY_LIST", "request": list_values})
                elif output["method"] == "SEND_BACKUP":
                    self.receive_backup(addr, output)
                    self.routingTableStatus[output["id"]] = [ALIVE, time()]
                elif output["method"] == "BACKUP_ACK":
                    # Stores the location of the backed-up image in the backupLocations dict
                    if output["id"] in self.backupLocations:
                        self.backupLocations[output["id"]].add(output["info"])
                    else:
                        self.backupLocations[output["id"]] = {output["info"]}

                    self.routingTableStatus[output["id"]] = [ALIVE, time()]
                    #In case all images belonging to this node have been backed up, it prints this message in the terminal
                    if len([x for v in self.backupLocations.values() for x in v]) == len(self.keystore[self.identification]):
                        print("Backup finished!")

            else:
                # timeout occurred, runs the stabilization protocol
                # If our node has images yet to be backed up, it will run the Backup Protocol instead
                images = self.check_backedup_images()

                if len(self.routingTable.keys()) >= 1 and images is not None:
                    self.set_backups(images)
                else:
                    self.stabilize()

    def __str__(self):
        return "Node ID: {}; DHT: {}; Routing Table Nodes: {}; backupLocations: {}".format(
            self.identification,
            self.inside_dht,
            self.routingTable,
            self.backupLocations,
        )

    def __repr__(self):
        return self.__str__()


def main(node_addr, folder, node_id, timeout, net_contact=None):
    """
        Launches the node.
        Parameters:
            node_addr: (Address, port) of the node
            node_id: ID of the node
            timeout: Timeout of the Stabilization protocol
            net_contact: (Address, Port) of a node already in the network. In case its None, this node will start the network.
    """
    logger = logging.getLogger("network")

    if net_contact == (None, None):
        node = DHTNode(node_addr, folder, node_id, timeout=timeout)
    else:
        node = DHTNode(node_addr, folder, node_id, net_contact, timeout=timeout)

    node.start()
    logger.info(node)

    # Await for the node to stop its activity
    node.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--savelog", default=True, action="store_false")
    parser.add_argument("folder", type=str, help="Folder name of the node to be started")
    parser.add_argument("node_id", type=int, help="ID of the node to be started")
    parser.add_argument("node_addr", type=str, help="Address of the node to be started")
    parser.add_argument("node_port", type=int, help="Port of the node to be started")
    parser.add_argument("-net_addr", type=str, help="Address of the node in the Network to be contacted for the JOIN_REQUEST")
    parser.add_argument("-net_port", type=int, help="Port of the node in the Network to be contacted for the JOIN_REQUEST")
    parser.add_argument("--timeout", type=int, default=15, help="Length of the timeout")
    args = parser.parse_args()

    logfile = {}
    filename = "./logs/node" + str(args.node_id) + "log.txt"
    if args.savelog:
        logfile = {"filename": filename, "filemode": "w"}

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
        datefmt="%m-%d %H:%M:%S",
        **logfile
    )

    logging.getLogger('PIL').setLevel(logging.WARNING)

    main(node_addr=(args.node_addr, args.node_port), node_id=args.node_id, net_contact=(args.net_addr, args.net_port),
         timeout=args.timeout, folder=args.folder)
