import streamlit as st
import pandas as pd
import json
import re
import time
from google import genai
from google.genai.errors import APIError

API_KEY = "AQ.Ab8RN6L7UO4NqURBJQJyKPIN9MXXiFKDqxgyn1PTcIqWE3hV5w"

st.set_page_config(page_title="Inteligentny Asystent Zakupowy & Kulinarny", layout="wide", initial_sidebar_state="expanded")

# Inicjalizacja stanu sesji
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "promotions_df" not in st.session_state:
    st.session_state.promotions_df = None

if "matrix_df" not in st.session_state:
    st.session_state.matrix_df = None

if "meal_plan_data" not in st.session_state:
    st.session_state.meal_plan_data = None

if "shared_shopping_list" not in st.session_state:
    st.session_state.shared_shopping_list = ""

if "last_context" not in st.session_state:
    st.session_state.last_context = ""

def clean_json_string(text):
    """Bezpieczne wyciąganie JSON bez problemów ze stringami."""
    text = text.strip()
    match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
    if match:
        return match.group(1)
    text = text.replace("```json", "").replace("
