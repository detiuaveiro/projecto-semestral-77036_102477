import logging
import pickle
import socket
import threading
import time
import sys
import argparse


class DHTNode(threading.Thread):
    """ DHT Node Agent. """

    def __init__(self, address, id, dht_address=None, timeout=3):
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

        self.routingTable = {}      # Dict that will keep the adresses of the other nodes in the mesh
        self.keystore = {}          # Where all data is stored
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

    def node_join(self, args):
        """Process JOIN_REQ message.
        Parameters:
            args (dict): addr and id of the node trying to join

        REPLY:
            JOIN_REP message with format: {'method': 'JOIN_REP',
            'routingTable': {'node_id': [node_addr, node_port]...}}
        """

        self.logger.debug("Node join: %s", args)
        recAddr = args["addr"]
        identification = args["id"]
        rt_reply = {}

        for node, addr in self.routingTable.items():
            rt_reply[node] = addr

        self.routingTable[identification] = recAddr
        self.send(recAddr, {"method": "JOIN_REP", "routingTable": rt_reply})

        self.logger.info(self)


    def stabilize(self, from_id, addr):
        """Process STABILIZE protocol.
            Updates all successor pointers.

        Parameters:
            from_id: id of the predecessor of node with address addr
            addr: address of the node sending stabilize message
        """
        '''
        self.logger.debug("Stabilize: %s %s", from_id, addr)
        if from_id is not None and contains(
                self.identification, self.successor_id, from_id
        ):
            # Update our successor
            self.successor_id = from_id
            self.successor_addr = addr

        # notify successor of our existence, so it can update its predecessor record
        args = {"predecessor_id": self.identification, "predecessor_addr": self.addr}
        self.send(self.successor_addr, {"method": "NOTIFY", "args": args})
        '''
        pass

    def get(self, key, address):
        pass

    def run(self):
        self.socket.bind(self.addr)

        # Loop until joining the DHT
        while not self.inside_dht:
            join_msg = {
                "method": "JOIN_REQ",
                "args": {"addr": self.addr, "id": self.identification},
            }
            self.send(self.dht_address, join_msg)
            payload, addr = self.recv()
            if payload is not None:
                output = pickle.loads(payload)
                self.logger.debug("O: %s", output)
                if output["method"] == "JOIN_REP":
                    """
                    JOIN_REP message with format: {'method': 'JOIN_REP',
                    'routingTable': {'node_id': [node_addr, node_port]...}}
                    """
                    neighborRT = output["routingTable"]

                    # Nó atualiza a sua routing Table com a informação recebida
                    self.routingTable = {key: (value[0], value[1]) for key, value in neighborRT.items()}

                    # Nó avisa vizinhos de que entrou na rede
                    for addr in self.routingTable.values():
                        hello_msg = {
                            "method": "HELLO",
                            "args": {"addr": self.addr, "id": self.identification},
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
                    self.node_join(output["args"])
                elif output["method"] == "GET":
                    self.get(output["args"]["key"], output["args"].get("from", addr))
                elif output["method"] == "STABILIZE":
                    # Initiate stabilize protocol
                    self.stabilize(output["args"], addr)
                elif output["method"] == "HELLO":
                    self.routingTable[output["args"]["id"]] = (output["args"]["addr"][0], output["args"]["addr"][1])
                    self.send(addr, {"method": "HELLO_ACK", })
                    self.logger.info(self)

            else:  # timeout occurred, lets run the stabilize algorithm
                # Ask successor for predecessor, to start the stabilize process
                #TODO: Update with new network configuration
                #self.send(self.successor_addr, {"method": "PREDECESSOR"})
                pass

    def __str__(self):
        #TODO: Add routing table
        return "Node ID: {}; DHT: {}; Routing Table: {}".format(
            self.identification,
            self.inside_dht,
            self.routingTable
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
    parser.add_argument("--timeout", type=int, default=3)
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
