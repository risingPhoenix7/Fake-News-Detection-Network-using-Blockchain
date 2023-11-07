import streamlit as st
from pyblock.wallet.transaction import *
from change_screen import *
def upload_file():
    uploaded_file = st.file_uploader("Upload a text file", type=["txt"])

    if uploaded_file is not None:
        # CREATE PARTIAL TRANSACTION
        partial_transaction = Transaction.generate_from_file(
            sender_wallet=st.session_state.p2pserver.wallet, file=uploaded_file, blockchain = st.session_state.p2pserver.blockchain)

        st.write("UPLOADED FILE: ", uploaded_file.name)
        # BROADCASE NEWLY CREATED TRANSACTION
        st.session_state.p2pserver.broadcast_transaction(
            partial_transaction)
        
        print("BROADCASTED TRANSACTION")
        
    # GO TO PREVIOUS SCREEN
    if st.button("Back"):
        # Set the previous screen in the session state
        change_screen(st.session_state.previous_screen)