import logging
import pickle
import socket
import threading
import time
import sys
import argparse


class DHTNode(threading.Thread):
    """ DHT Node Agent. """

    def __init__(self, address, id, dht_address=None, timeout=10):
        """Constructor

        Parameters:
            address: self's address
            dht_address: address of a node in the DHT
            timeout: impacts how often stabilize algorithm is carried out
        """
        threading.Thread.__init__(self)
        self.done = False
        self.identification = id
        self.addr = address  # My address
        self.dht_address = dht_address  # Address of the initial Node
        if dht_address is None:
            self.inside_dht = True
        else:
            self.inside_dht = False

        self.routingTable = {}              # Dict that will keep the adresses of the other nodes in the mesh
        self.routingTableStatus = {}        # Dict that will keep the connection status of the other nodes in the mesh
        self.keystore = {}                  # Where all data is stored {id: [hash,...]}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(timeout)
        self.logger = logging.getLogger("Node {}".format(self.identification))

    def send(self, address, msg):
        """ Send msg to address. """
        payload = pickle.dumps(msg)
        self.socket.sendto(payload, address)

    def recv(self):
        """ Retrieve msg payload and from address."""
        try:
            payload, addr = self.socket.recvfrom(1024)
        except socket.timeout:
            return None, None

        if len(payload) == 0:
            return None, addr
        return payload, addr

    def node_join(self, args, recKeystore):
        """Process JOIN_REQ message.
        Parameters:
            args (dict): addr and id of the node trying to join

        REPLY:
            JOIN_REP message with format: {'method': 'JOIN_REP',
            'args': {'addr':addr, 'id':id},
            'routingTable': {'node_id': [node_addr, node_port]...}}
        """

        self.logger.debug("Node join: %s", args)
        recAddr = args["addr"]
        identification = args["id"]
        rt_reply = {}

        for node, addr in self.routingTable.items():
            rt_reply[node] = addr

        self.routingTable[identification] = recAddr
        self.routingTableStatus[identification] = True
        self.keystore[identification] = recKeystore
        self.send(recAddr, {"method": "JOIN_REP", "args": {'addr':self.addr, 'id':self.identification}, "routingTable": rt_reply, "keystore": self.keystore})

        self.logger.info(self)

    def stay_alive(self):
        """
        Part of the Stabilization protocol.
        Sends an ALIVE message to all the nodes in the Routing Table to check if they're still active.
        Afterwards, it sets the status of all nodes to False (Dead). The status will be reset to True if they reply with
        an ALIVE_ACK message.
        """
        for node, addr in self.routingTable.items():
            hello_msg = {
                "method": "ALIVE",
                "args": {"addr": self.addr, "id": self.identification},
            }
            self.send(addr, hello_msg)
            self.routingTableStatus[node] = False

    def check_alive(self):
        """
            Part of the Stabilization protocol.
            Checks all the nodes in the routing table to see if they're still alive. Removes them from the routing table if
        they're not.
        """
        for node, status in self.routingTableStatus.items():
            if not status:
                self.routingTableStatus.pop(node)
                self.routingTable.pop(node)

        self.logger.info(self)

    def get(self, key, address):
        pass

    def get_key(self, val):
        for key, value in self.keystore.items():
            if val in value:
                return key

        return "key doesn't exist"

    def run(self):
        self.socket.bind(self.addr)

        # Insert node values (photos hash) in shared data structure
        self.keystore[self.identification] = ["Hello" + str(self.identification)]

        # Loop until joining the DHT
        while not self.inside_dht:
            join_msg = {
                "method": "JOIN_REQ",
                "args": {"addr": self.addr, "id": self.identification},
                "keystore" : self.keystore[self.identification],
            }
            self.send(self.dht_address, join_msg)
            payload, addr = self.recv()
            if payload is not None:
                output = pickle.loads(payload)
                self.logger.debug("O: %s", output)
                if output["method"] == "JOIN_REP":
                    # JOIN_REP message with format: {'method': 'JOIN_REP',
                    # 'args': {'addr':addr, 'id':id},
                    # 'routingTable': {'node_id': [node_addr, node_port]...}}
                    neighborRT = output["routingTable"]
                    # Nó atualiza a sua routing Table com a informação recebida
                    # Adição dos Nós Recebidos na Mensagem
                    self.routingTable = {key: (value[0], value[1]) for key, value in neighborRT.items()}
                    self.routingTableStatus = {key: True for key in neighborRT.keys()}
                    # Adição do Nó Base
                    self.routingTable[output["args"]["id"]] = (output["args"]["addr"][0], output["args"]["addr"][1])
                    self.routingTableStatus[output["args"]["id"]] = True

                    self.keystore = output["keystore"]

                    # Nó avisa vizinhos de que entrou na rede
                    for addr in self.routingTable.values():
                        hello_msg = {
                            "method": "HELLO",
                            "args": {"addr": self.addr, "id": self.identification},
                            "keystore": self.keystore[self.identification]
                        }
                        self.send(addr, hello_msg)

                    self.inside_dht = True
                    self.logger.info(self)

        while not self.done:
            payload, addr = self.recv()
            if payload is not None:
                output = pickle.loads(payload)
                self.logger.info("O: %s", output)
                if output["method"] == "JOIN_REQ":
                    self.node_join(output["args"], output["keystore"])
                elif output["method"] == "HELLO":
                    #Adição do Nó à Routing Table
                    self.routingTable[output["args"]["id"]] = (output["args"]["addr"][0], output["args"]["addr"][1])
                    self.routingTableStatus[output["args"]["id"]] = True
                    self.keystore[output["args"]["id"]] = output["keystore"]
                    # Sending the Reply
                    self.send(addr, {"method": "HELLO_ACK", })
                    self.logger.info(self)
                elif output["method"] == "ALIVE":
                    # Sends an ALIVE_ACK message notifying self is alive
                    ack_msg = {
                        "method": "ALIVE_ACK",
                        "args": {"addr": self.addr, "id": self.identification},
                    }
                    self.send(addr, ack_msg)
                elif output["method"] == "ALIVE_ACK":
                    # Changes the status of the sender to alive in the Routing Table
                    self.routingTableStatus[output["args"]["id"]] = True
                elif output["method"] == "REQUEST_IMG":
                    # handles the request for an image
                    if output["request"] in self.keystore[self.identification] and "args" not in output.keys():
                        self.logger.info(output["request"])
                        self.send(addr, {"method": "REPLY_IMG", "request": self.keystore[self.identification]})
                    elif "args" in output.keys():
                        self.logger.info(output["args"])
                        self.send(output["args"], {"method": "REPLY_IMG", "request": self.keystore[self.identification]})
                    else:
                        self.send(self.routingTable[self.get_key(output["request"])], {"method": "REQUEST_IMG", "args": addr, "request": output["request"]})
                elif output["method"] == "REQUEST_LIST":
                    # handles the request the list of images per node
                    values = self.keystore.values()
                    list_values = []
                    for x in values:
                        list_values += [y for y in x if y not in list_values]
                    self.send(addr, {"method": "REPLY_LIST", "request": list_values})
            else:  # timeout occurred, lets run the stabilize protocol
                self.check_alive()
                self.stay_alive()

    def __str__(self):
        return "Node ID: {}; DHT: {}; Routing Table Nodes: {}; Keystore: {}".format(
            self.identification,
            self.inside_dht,
            self.routingTable,
            self.keystore,
        )

    def __repr__(self):
        return self.__str__()


def main(number_nodes, timeout):
    """ Script to launch several DHT nodes. """

    # logger for the main
    logger = logging.getLogger("DHT")
    # list with all the nodes
    dht = []
    # initial node on DHT
    node = DHTNode(("localhost", 5000), 0)
    node.start()
    dht.append(node)
    logger.info(node)

    for i in range(number_nodes - 1):
        time.sleep(0.2)
        # Create DHT_Node threads on ports 5001++ and with initial DHT_Node on port 5000
        node = DHTNode(("localhost", 5001 + i), i+1, ("localhost", 5000), timeout)
        node.start()
        dht.append(node)
        logger.info(node)

    # Await for DHT to get stable
    time.sleep(10)

    # Await for all nodes to stop
    for node in dht:
        node.join()


if __name__ == "__main__":
    # Launch DHT with 5 Nodes

    parser = argparse.ArgumentParser()
    parser.add_argument("--savelog", default=False, action="store_true")
    parser.add_argument("--nodes", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    logfile = {}
    if args.savelog:
        logfile = {"filename": "dht.txt", "filemode": "w"}

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
        datefmt="%m-%d %H:%M:%S",
        **logfile
    )

    main(args.nodes, timeout=args.timeout)
