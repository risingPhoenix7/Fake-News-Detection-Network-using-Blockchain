import json
import websocket
from pyblock.blockchain.blockchain import Blockchain
from pyblock.wallet.wallet import Wallet
from pyblock.wallet.transaction_pool import TransactionPool
from websocket_server import WebsocketServer
from typing import Type
import pyblock.config as config
import pyblock.chainutil as ChainUtil

P2P_PORT = int(config.P2P_PORT)
PEERS = config.PEERS

MESSAGE_TYPE = {
    'chain': 'CHAIN',
    'block': 'BLOCK',
    'transaction': 'TRANSACTION',
    'clear_transactions': 'CLEAR_TRANSACTIONS',
    'new_validator': 'NEW_VALIDATOR',
    'login': 'LOGIN',

}


class P2pServer:
    def __init__(self, blockchain: Type[Blockchain], transaction_pool: Type[TransactionPool], wallet: Type[Wallet]):
        self.blockchain = blockchain
        self.sockets = []
        self.validator_sockets = []
        self.transaction_pool = transaction_pool
        self.wallet = wallet
        self.challenges = {}

    def listen(self):
        print("Starting p2p server...")
        self.server = WebsocketServer(port=P2P_PORT,host="0.0.0.0")
        self.server.set_fn_new_client(self.new_client)
        self.server.set_fn_client_left(self.client_left)
        self.server.set_fn_message_received(self.message_received)
        self.connect_to_peers()
        self.server.run_forever()

    def new_client(self, client, server):
        print("Socket connected:", client['id'])
        self.sockets.append(client)
        self.send_chain(client)

    def client_left(self, client, server):
        print(client)
        print("Client left:", client['id'])
        self.sockets.remove(client)

    def message_received(self, client, server, message):
        data = json.loads(message)
        print("Received data from peer:", data["type"])

        if data["type"] == MESSAGE_TYPE["chain"]:
            self.blockchain.replace_chain(data["chain"])
            
        elif data["type"] == MESSAGE_TYPE["transaction"]:
            if not self.transaction_pool.transaction_exists(data["transaction"]):
                self.transaction_pool.add_transaction(data["transaction"])
                self.broadcast_transaction(data["transaction"])
                if self.transaction_pool.threshold_reached():
                    if self.blockchain.get_leader() == self.wallet.get_public_key():
                        block = self.blockchain.create_block(
                            self.transaction_pool.transactions, self.wallet)
                        self.broadcast_block(block)
        elif data["type"] == MESSAGE_TYPE["block"]:
            if self.blockchain.is_valid_block(data["block"]):
                self.broadcast_block(data["block"])
                self.transaction_pool.clear()
            # TODO: Add logic to handle invalid block and penalise the validator
        elif data["type"] == MESSAGE_TYPE["new_validator"]:
            # Assuming the new validator sends their public key with this message
            new_validator_public_key = data["public_key"]
            
            # Check if the public key is already known or not
            if new_validator_public_key not in self.known_validators:
                # Send a challenge to the new validator
                self.send_challenge(client, new_validator_public_key)
            else:
                # The public key is already known, so no need to verify it again
                # You could handle this case as you see fit, perhaps logging it or sending a response

    def verify_new_validator(self, public_key: str, signature: str, challenge: str):
        # Verify the signature against the challenge using ChainUtil
        return ChainUtil.verify_signature(public_key, signature, ChainUtil.hash(challenge))

    def send_challenge(self, client_socket, public_key: str):
        # Generate a challenge
        challenge = ChainUtil.hash(ChainUtil.id())  # Could be any unique piece of data
        # Store the challenge somewhere to verify it later when the signature comes back
        self.challenges[public_key] = challenge

        # Send the challenge to the validator
        message = json.dumps({
            "type": "CHALLENGE",
            "public_key": public_key,
            "challenge": challenge
        })
        self.server.send_message(client_socket, message)

    def handle_challenge_response(self, client_socket, message):
        # Extract the public key, signature, and challenge from the message
        public_key = message['public_key']
        signature = message['signature']
        challenge = self.challenges.get(public_key)

        # Verify the signature
        if challenge and self.verify_new_validator(public_key, signature, challenge):
            # The validator has been verified
            print(f"Validator with public key {public_key} has been successfully verified.")
            # Here you would add the validator to the list of known validators
        else:
            # The validation failed
            print(f"Failed to verify validator with public key {public_key}.")

        # Remove the challenge from the storage as it's no longer needed
        if public_key in self.challenges:
            del self.challenges[public_key]
    
    def send_challenge_response(self, validator_socket, public_key: str, challenge: str):
    # The validator would create a signature for the challenge
        signing_key, _ = ChainUtil.gen_key_pair()
        signature = signing_key.sign(challenge.encode()).signature.hex()

        # Send the signature back as a response to the challenge
        message = json.dumps({
            "type": "CHALLENGE_RESPONSE",
            "public_key": public_key,
            "signature": signature
        })
        self.server.send_message(validator_socket, message)
        
    def connect_to_peers(self):
        for peer in PEERS:
            try:
                socket_app = websocket.WebSocketApp(peer,
                                                    on_message=self.on_peer_message,
                                                    on_close=self.on_peer_close,
                                                    on_open=self.on_peer_open)
                socket_app.run_forever()
            except Exception as e:
                print(f"Failed to connect to peer {peer}. Error: {e}")

    def on_peer_message(self, ws, message):
        self.message_received(ws, None, message)

    def on_peer_close(self, ws, *args):
        pass

    def on_peer_open(self, ws):
        pass

    def send_chain(self, socket):
        chain_as_json = [block.to_json() for block in self.blockchain.chain]
        message = json.dumps({
            "type": MESSAGE_TYPE["chain"],
            "chain": chain_as_json
        })
        self.server.send_message(socket, message)


    def sync_chain(self):
        for socket in self.sockets:
            self.send_chain(socket)

    def broadcast_transaction(self, transaction):
        for socket in self.sockets:
            self.send_transaction(socket, transaction)

    def send_transaction(self, socket, transaction):
        message = json.dumps({
            "type": MESSAGE_TYPE["transaction"],
            "transaction": transaction
        })
        self.server.send_message(socket, message)

    def broadcast_block(self, block):
        for socket in self.sockets:
            self.send_block(socket, block)

    def send_block(self, socket, block):
        message = json.dumps({
            "type": MESSAGE_TYPE["block"],
            "block": block
        })
        self.server.send_message(socket, message)

# if __name__ == "__main__":
#     blockchain = Blockchain()
#     transaction_pool = TransactionPool()
#     wallet = Wallet()
#     p2p_server = P2pServer(blockchain, transaction_pool, wallet)
#     p2p_server.listen()
