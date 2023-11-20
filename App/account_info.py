from pyblock.wallet.transaction import *
import streamlit as st
from change_screen import *


def show_account_info():
    if st.session_state.screen == "account_info":
        st.markdown(
            "<h1 style='text-align: center;'>ACCOUNT INFORMATION</h1>",
            unsafe_allow_html=True
        )
        #GET USER'S DETAILS
        public_key = st.session_state.p2pserver.wallet.get_public_key()
        private_key = st.session_state.p2pserver.wallet.get_private_key()
        balance = st.session_state.blockchain.get_balance(
            public_key
        )
        stake = st.session_state.blockchain.get_stake(public_key)
        
        #DISPLAY THE DETAILS
        st.write("Current Reputation = ", balance + stake)
        st.write("Current Balance = ", balance)
        if st.session_state.user_type == "Auditor":
            st.write("Currrent Stake in Network = ", stake)
        
        
        with st.expander("Click to view private key"):
            st.write(private_key)
            
        with st.expander("Click to view public key"):
            st.write(public_key)

        if st.button("Back"):
            with st.spinner("Please Wait"): 
                change_screen(st.session_state.previous_screen)
