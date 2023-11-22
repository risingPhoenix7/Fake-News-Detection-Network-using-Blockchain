import json
from pyblock.blockchain.blockchain import Blockchain
from pyblock.blockchain.block import *
from pyblock.wallet.wallet import Wallet
from pyblock.wallet.transaction_pool import TransactionPool
from typing import Type
from pyblock.chainutil import *
from pyblock.wallet.transaction import *
from pyblock.blockchain.account import *
from pyblock.heartbeat_manager import *
import requests
import zmq
import logging
import threading
import socket
import random as random


MESSAGE_TYPE = {
    'chain': 'CHAIN',
    'block': 'BLOCK',
    'transaction': 'TRANSACTION',
    'new_validator': 'NEW_VALIDATOR',
    'vote': 'VOTE',
    "block_proposer_address": "BLOCK_PROPOSER_ADDRESS",
    "new_node": "NEW_NODE"
}
# to handle self.... self.message_received(None, None, message)
logging.basicConfig(level=logging.INFO)
# Configuration
server_url = 'http://65.1.130.255/app'  # Local server URL
send_timeout = 5000
receive_timeout = 5000
heartbeat_timeout = 30  # seconds, adjust as needed


class P2pServer:
    def __init__(self, blockchain: Type[Blockchain], transaction_pool: Type[TransactionPool], wallet: Type[Wallet], user_type="Reader"):
        self.blockchain = blockchain
        self.transaction_pool = transaction_pool
        self.wallet = wallet  # assuming initialised wallet
        self.accounts = blockchain.accounts
        self.user_type = user_type
        self.received_block = None
        self.block_received = None
        self.block_proposer = None
        self.peers = {}  # map of clientPort to dictionary of lastcontacted and public key
        self.myClientPort = 0
        self.context = zmq.Context()
        self.heartbeat_manager = None
        
        #IF THE P2PSERVER HAS RECEIVED CURRENT TRANSACTION POOL & CHAIN ETC.
        self.initialised = False

    def private_send_message(self, clientPort, message):
        reply = None
        # assumes message is encrypted
        zmq_socket = self.context.socket(zmq.REQ)
        # Receive timeout in milliseconds
        zmq_socket.setsockopt(zmq.RCVTIMEO, receive_timeout)
        # Send timeout in milliseconds
        zmq_socket.setsockopt(zmq.SNDTIMEO, send_timeout)
        try:
            tcpaddr = f"tcp://{clientPort}"
            print(f"Sending message to {tcpaddr}")
            zmq_socket.connect(tcpaddr)
            zmq_socket.send_string(message)
            reply = zmq_socket.recv_string()
            print(f"Received reply from {clientPort}: {reply}")
        except Exception as e:
            reply = f"Failed to send message {message} to {clientPort}: {e}"
        finally:
            zmq_socket.close()
        return reply

    def get_encrypted_message(self, message):
        message['clientPort'] = self.myClientPort  # Add the clientPort
        encrypted_message = ChainUtil.encryptWithSoftwareKey(
            message)  # Re-encode and encrypt
        return encrypted_message

    def register(self, public_key, clientPort):
        print("Registering with public key and address")
        data = {'public_key': public_key, 'address': clientPort}
        try:
            response = requests.post(f'{server_url}/register', json=data)
            print(f"Register api. Response from server: {response}")
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Registration failed: {e}")
            return None

    def get_ip_address(self):
        print("Getting IP address")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip_address = s.getsockname()[0]
                print(f"Obtained IP address: {ip_address}")
                return ip_address
        except Exception as e:
            logging.error(f"Error obtaining IP address: {e}")
            return None

    def is_port_available(self, port):
        print(f"Checking if port {port} is available")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            a = s.connect_ex(('localhost', port)) != 0
            print(a)
            return a

    def start_server(self):
        while True:
            port = random.randint(50000, 65533)
            if self.is_port_available(port) and self.is_port_available(port+1):
                try:
                    ip_address = self.get_ip_address()
                    if ip_address is None:
                        print("Failed to obtain IP address. Server cannot start.")
                        return

                    self.myClientPort = f"{ip_address}:{port}"
                    zmq_socket = self.context.socket(zmq.REP)
                    zmq_socket.bind(f"tcp://{self.myClientPort}")
                    break  # Exit the loop if binding is successful

                except zmq.ZMQError as e:
                    print(f"Failed to bind to port {port}: {e}")
                    # Optionally, you could add a short delay here before retrying
                    time.sleep(1)
            else:
                print(f"Port {port} is not available. Trying another port.")

        self.register(clientPort=f"{ip_address}:{port}",
                      public_key=self.wallet.get_public_key())

        self.get_peers()
        print("Starting heartbeat manager")
        self.heartbeat_manager = HeartbeatManager(
            myClientPort=self.myClientPort, peers=self.peers, server_url=server_url, accounts=self.accounts)
        heartbeat_thread = threading.Thread(
            target=self.heartbeat_manager.run, daemon=True)
        heartbeat_thread.start()
        print("Heartbeat manager started")
        while not self.heartbeat_manager.one_time:
            time.sleep(0.5)
        print("Creating new thread since heartbeat manager has run once")
        thread = threading.Thread(target=self.broadcast_new_node)
        thread.start() 

        self.initialised = True
        print("New thread started")
        
        while True:
            message = zmq_socket.recv_string()
            zmq_socket.send_string(
                f"Successfully received message {message}. Sent from {self.myClientPort}")
            self.message_received(message)

    def broadcast_message(self, message):
        print("Broadcasting message")
        responses = []
        encrypted_message = self.get_encrypted_message(message)
        print(f"Peers: {self.peers}")
        for (clientPort, data) in self.peers.copy().items():
            if (clientPort != self.myClientPort):
                responses.append(self.private_send_message(
                    clientPort, encrypted_message))
            else:
                responses.append(self.privateSendToSelf(encrypted_message))

        return responses

    def privateSendToSelf(self, message):
        print("Sending private message to self")
        try:
            self.message_received(message)
            return f"Private..Successfully received message {message}. Sent from {self.myClientPort}"
        except Exception as e:
            return f"Failed to send message {message} to self: {e}"

    def send_direct_encrypted_message(self, message, clientPort):
        print("Sending direct message")
        encrypted_message = self.get_encrypted_message(message)
        if (clientPort == self.myClientPort):
            return self.privateSendToSelf(encrypted_message)
        return self.private_send_message(clientPort, encrypted_message)

    def get_peers(self):
        print("Fetching peers")
        try:
            response = requests.get(f'{server_url}/peers')
            response.raise_for_status()
            peers_list = response.json()
            print(f"Received peers: {peers_list}")
            for peer in peers_list:
                self.peers[peer['address']] = {
                    'lastcontacted': time.time(),
                    'public_key': peer['public_key']
                }

        except requests.RequestException as e:
            logging.error(f"Failed to fetch peers: {e}")
            print('Failed to fetch peers')

    def listen(self):
        print("Starting tcp server...")
        server_thread = threading.Thread(
            target=self.start_server, daemon=True)
        server_thread.start()
        print("Server thread started")

    def send_current_block_proposer(self, clientPort):
        message = {
            "type": MESSAGE_TYPE["block_proposer_address"],
            "address": self.block_proposer
        }

        self.send_direct_encrypted_message(message, clientPort)

    # FUNCTION CALLED WHEN A CLIENT LEAVES SERVER

    # def client_left(self, client, server):
    #     print("Client left:", client['id'])

    #     # REMOVE CLIENT FROM CONNECTIONS
    #     self.connections.remove(client)
    #     # self.accounts.clientLeft(clientport=client)

    # FUNCTION CALLED WHEN A MESSAGE IS RECIEVED FROM ANOTHER CLIENT
    def message_received(self, message):
        print(f"Received message: {message}")

        try:
            # CONVERT FROM JSON TO DICTIONARY
            data = json.loads(message)

        except json.JSONDecodeError:
            print("Failed to decode JSON")
            return

        # CHECK IF SIGNATURE IS VALID
        if not ChainUtil.decryptWithSoftwareKey(data):
            print("Invalid message recieved.")
            return

        clientPort = data["clientPort"]

        print("MESSAGE RECIEVED OF TYPE", data["type"])

        # IF BLOCKCAIN RECIEVED
        if data["type"] == MESSAGE_TYPE["chain"]:
            # TRY TO REPLACE IF LONGER CHAIN
            
            ret = self.blockchain.replace_chain(data["chain"])
            
            # IF NOT THE LONGEST CHAIN; DONT REPLACE ANYTHING ELSE AS THIS NODE'S DATA IS CLEARLY OUTDATED
            if not ret:
                return
            
            print("REPLACED CHAIN")
            
            self.accounts.from_json(json_data=data["accounts"])
            print("REPLACED ACCOUNTS")
            
            print(self.accounts.to_json())
            
            self.transaction_pool = TransactionPool.from_json(
                data["transaction_pool"])
            print("REPLACED TRANSACTION POOL")
            print(self.transaction_pool)
            
            # SET INITIALISED TO TRUE AND ALLOW USER TO GO TO MAIN PAGE
            if not self.initialised:
                self.initialised = True

        elif data["type"] == MESSAGE_TYPE["transaction"]:
            # CREATE TRANSACTION FROM JSON FORM
            transaction = Transaction.from_json(data["transaction"])

            # IF DOESN'T EXIST; ADD IT [VALIDATED AT TIME OF BLOCK RECIEVED]
            self.transaction_pool.add_transaction(transaction)

            # ADD TO TRANSACTIONS SENT BY A USER TO VIEW
            self.accounts.add_transaction(transaction)

        elif data["type"] == MESSAGE_TYPE["block"]:
            # CHECK BLOCK IS PROPOSED BY CURRENT BLOCK PROPOSER
            block = Block.from_json(data["block"])

            print(block.transactions)
            if self.block_proposer != block.validator:
                print("RECEIVED BLOCK DOESN'T HAVE CORRECT VALIDATOR!")
                return

            # CHECK VALIDITY OF BLOCK & ITS TRANSACTIONS
            if (self.blockchain.is_valid_block(
                    block, self.transaction_pool, self.accounts)):

                # SET RECIEVED FLAG TO ALLOW VOTING
                self.block_received = True
                self.voted = False
                self.received_block = block
                self.accounts.add_sent_block(block.validator, block)

            else:
                print("RECEIVED BLOCK DEEMED INVALID.")

        elif data["type"] == MESSAGE_TYPE["new_validator"]:
            # NEW VALIDATOR
            new_validator_public_key = data["public_key"]
            new_validator_stake = data["stake"]

            # CHECK & MAKE THE ACCOUNT A VALIDATOR
            self.accounts.makeAccountValidatorNode(
                address=new_validator_public_key, stake=new_validator_stake
            )

        elif data["type"] == MESSAGE_TYPE["new_node"]:
            clientPort = data["clientPort"]
            self.heartbeat_manager.addToClients(clientPort, data["public_key"])
            self.accounts.addANewClient(
                address=data["public_key"], clientPort=clientPort, userType=self.user_type)
            
            if (clientPort != self.myClientPort):
                self.send_chain(clientPort)


        elif data["type"] == MESSAGE_TYPE["vote"]:
            self.handle_votes(data)

        elif data["type"] == MESSAGE_TYPE["block_proposer_address"]:
            # SET THE CURRENT BLOCK PROPOSER ACC. TO MESSAGE
            self.block_proposer = data["address"]

    def handle_votes(self, data):
        # CHECK IF THE VOTE IS VALID [FROM AN ACTIVE VALIDATOR]
        if not self.accounts.accounts[data["address"]].isActive or not self.accounts.accounts[data["address"]].isValidator:
            print("INVALID VOTE")
            return

        # IF NOT CURRENT BLOCK
        if data["block_index"] != self.received_block.index:
            print("OLD VOTE RECEIVED")
            return

        # INCREMENT NUMBER OF VOTES FOR THE BLOCK
        self.received_block.votes.add(data["address"])
        votes = data["votes"]

        # INCREMENT VOTES FOR THE TRANSACTIONS
        transactions_dict = {
            transaction.id: transaction for transaction in self.received_block.transactions
        }

        for key, value in votes:
            if value == "True":
                transactions_dict[key].positive_votes.add(data["address"])
            else:
                transactions_dict[key].negative_votes.add(data["address"])

        # JUST IN CASE OF PASS BY VALUE
        for index, transaction in enumerate(self.received_block.transactions):
            self.received_block.transactions[index] = self.trasaction_dict[transaction.id]

    def broadcast_new_validator(self, stake):
        """
        Broadcast the new validator's public key to all connected nodes.
        """
        # try:
        # self.accounts.makeAccountValidatorNode(address=self.wallet.get_public_key(),stake=stake)
        # TODO: check if self message works
        message = {
            "type": MESSAGE_TYPE["new_validator"],
            "public_key": self.wallet.get_public_key(),
            "stake": stake
        }

        self.broadcast_message(message)

    def send_new_validator(self, clientPort, public_key: str, stake):
        """
        Send a new validator's public key to the specified socket.
        """
        message = {
            "type": MESSAGE_TYPE["new_validator"],
            "public_key": public_key,
            "stake": stake
        }

        self.send_direct_encrypted_message(message, clientPort=clientPort)

    def broadcast_new_node(self):
        """
        Broadcast a new node message.
        """
        message = {
            "type": MESSAGE_TYPE["new_node"],
            "public_key": self.wallet.get_public_key(),
            "clientPort": self.myClientPort
        }
        self.broadcast_message(message)

    def send_chain(self, clientPort):
        chain_as_json = [block.to_json() for block in self.blockchain.chain]
        message = {
            "type": MESSAGE_TYPE["chain"],
            "chain": chain_as_json,
            "accounts": self.accounts.to_json(),
            "transaction_pool": self.transaction_pool.to_json()
        }
        print(message["transaction_pool"])
        # also print its type
        print("\n \n type of transaction pool")
        print(type(message["transaction_pool"]))
        self.send_direct_encrypted_message(
            message=message, clientPort=clientPort)

    def broadcast_transaction(self, transaction):
        message = {
            "type": MESSAGE_TYPE["transaction"],
            "transaction": transaction.to_json()
        }
        self.broadcast_message(message)

    def broadcast_block(self, block):
        message = {
            "type": MESSAGE_TYPE["block"],
            "block": block.to_json()
        }
        self.broadcast_message(message)

    def broadcast_votes(self, votes_dict):
        votes_list = [(key, value) for key, value in votes_dict.items()]

        # Prepare the message content without the signature
        message_content = {
            "type": MESSAGE_TYPE["vote"],
            "address": self.wallet.get_public_key(),
            "votes": votes_list,
            "block_index": self.received_block.index
        }

        # # Convert the message content to a JSON string
        message_json = json.dumps(message_content, cls=CustomJSONEncoder)

        # Sign the JSON string
        signature = self.wallet.sign(message_json)

        # Append the signature to the message content
        message_content['signature'] = signature

        # Convert the full message with signature to JSON

        # self.message_received(None, None, message)

        self.broadcast_message(message_content)

    def endserver(self):
        self.heartbeat_manager.stop()
        self.heartbeat_manager = None
        self.peers = {}
        self.myClientPort = 0
        self.block_proposer = None
        self.block_received = None
        self.received_block = None
        self.blockchain = Blockchain()
        self.transaction_pool = TransactionPool()
        self.wallet = Wallet(
            private_key=None, name=None, email=None
        )
        self.context.destroy()
        self.accounts = Accounts()
