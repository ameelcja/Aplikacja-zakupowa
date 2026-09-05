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

def get_supported_models(client):
    active_models = []
    try:
        for m in client.models.list():
            name = getattr(m, 'name', '')
            if 'flash' in name.lower():
                active_models.append(name.replace('models/', ''))
    except Exception:
        pass
    
    preferred_order = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
    sorted_models = [m for m in preferred_order if m in active_models]
    for m in active_models:
        if m not in sorted_models:
            sorted_models.append(m)
            
    return sorted_models if sorted_models else preferred_order

def generate_with_fallback(client, prompt):
    candidate_models = get_supported_models(client)
    last_err = None

    for model_name in candidate_models:
        for _ in range(2):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return resp.text
            except APIError as e:
                last_err = e
                if e.code in [503, 429]:
                    time.sleep(2)
                    continue
                break
            except Exception as e:
                last_err = e
                if "503" in str(e) or "429" in str(e):
                    time.sleep(2)
                    continue
                break

    raise RuntimeError(f"Błąd połączenia z modelem AI: {last_err}")

# ==========================================
# PASEK BOCZNY - NAWIGACJA
# ==========================================
st.sidebar.title("🧭 Menu Aplikacji")

menu_choice = st.sidebar.radio(
    "Wybierz moduł:",
    [
        "🍳 Planer posiłków i przepisów",
        "🏷️ Lista zakupów z promocjami",
        "📊 Lista na podstawie wag",
        "💬 Asystent AI"
    ]
)

st.sidebar.markdown("---")
st.sidebar.caption("🛒 **Inteligentny Asystent Zakupowy**\nPlanowanie dań, optymalizacja Lidl/Auchan i wielokryterialna priorytetyzacja.")

# ==========================================
# MODUŁ 1: PLANER POSIŁKÓW I PRZEPISÓW (NOWOŚĆ)
# ==========================================
if menu_choice == "🍳 Planer posiłków i przepisów":
    st.title("🍳 Planer Posiłków & Generator Listy Zakupów")
    st.write("AI zaplanuje dla Ciebie śniadania, obiady i kolacje, poda zwięzłe przepisy i wygeneruje kompletną listę zakupów.")

    col1, col2 = st.columns([1, 2])
    with col1:
        days_count = st.slider("Liczba dni:", min_value=1, max_value=7, value=3)
        diet_type = st.selectbox(
            "Styl żywienia:",
            ["Zrównoważona / Standardowa", "Wysokobiałkowa (High-Protein)", "Wegetariańska", "Szybka i prosta (do 20 min)", "Ekonomiczna / Budżetowa"]
        )
    with col2:
        preferences = st.text_input(
            "Preferencje kulinarne, wykluczenia lub składniki:",
            placeholder="np. wytrawne śniadania, dużo warzyw, bez owoców morza, lubię dania z kurczakiem"
        )

    def generate_meal_plan(days, diet, prefs):
        client = genai.Client(api_key=API_KEY)
        prompt = f"""
        Jesteś profesjonalnym dietetykiem i szefem kuchni w Polsce.
        Przygotuj zrównoważony jadłospis na {days} dni:
        - Styl: {diet}
        - Uwagi/preferencje: {prefs if prefs else "brak szczególnych"}

        Dla każdego dnia uwzględnij 3 posiłki: Śniadanie, Obiad, Kolacja.
        Dla każdego posiłku podaj: nazwę dania, listę składników (z gramaturą/ilością) oraz krótki, 2-3 zdaniowy przepis wykonania.
        Na koniec stwórz zsumowaną, skonsolidowaną listę wszystkich unikalnych artykułów spożywczych niezbędnych do zrobienia zakupów w polskim sklepie (np. jajka, mleko owsiane, pomidory, pierś z kurczaka).

        Zwróć WYŁĄCZNIE czysty format JSON bez bloków markdown:
        {{
          "dni": [
            {{
              "dzien": 1,
              "sniadanie": {{"nazwa": "...", "skladniki": ["..."], "przepis": "..."}},
              "obiad": {{"nazwa": "...", "skladniki": ["..."], "przepis": "..."}},
              "kolacja": {{"nazwa": "...", "skladniki": ["..."], "przepis": "..."}}
            }}
          ],
          "lista_zakupow": ["jajka", "chleb żytni", "pomidory malinowe", "oliwa z oliwek", "pierś z kurczaka"]
        }}
        """
        raw = generate_with_fallback(client, prompt)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(raw.replace("```json", "").replace("```", "").strip())

    if st.button("✨ Zaplanuj posiłki i stwórz listę zakupów"):
        with st.spinner("AI komponuje jadłospis, przepisy i optymalizuje listę składników..."):
            try:
                plan = generate_meal_plan(days_count, diet_type, preferences)
                st.session_state.meal_plan_data = plan
                st.session_state.shared_shopping_list = ", ".join(plan.get("lista_zakupow", []))
                
                # Zapis kontekstu do czatu
                summary_plan = []
                for d in plan.get("dni", []):
                    summary_plan.append(f"Dzień {d['dzien']}: Śniadanie: {d['sniadanie']['nazwa']}, Obiad: {d['obiad']['nazwa']}, Kolacja: {d['kolacja']['nazwa']}")
                st.session_state.last_context = "JADŁOSPIS:\n" + "\n".join(summary_plan) + "\nSKŁADNIKI: " + st.session_state.shared_shopping_list
            except Exception as e:
                st.error(f"Błąd generowania jadłospisu: {e}")

    if st.session_state.meal_plan_data:
        plan = st.session_state.meal_plan_data
        
        st.markdown("---")
        st.subheader("📋 Zaplanowany Jadłospis & Przepisy")
        
        for d in plan.get("dni", []):
            with st.expander(f"📅 Dzień {d.get('dzien', 1)}", expanded=True):
                col_s, col_o, col_k = st.columns(3)
                
                with col_s:
                    st.markdown("#### 🍳 Śniadanie")
                    st.write(f"**{d['sniadanie']['nazwa']}**")
                    st.caption(f"Składniki: {', '.join(d['sniadanie']['skladniki'])}")
                    st.info(d['sniadanie']['przepis'])

                with col_o:
                    st.markdown("#### 🍲 Obiad")
                    st.write(f"**{d['obiad']['nazwa']}**")
                    st.caption(f"Składniki: {', '.join(d['obiad']['skladniki'])}")
                    st.info(d['obiad']['przepis'])

                with col_k:
                    st.markdown("#### 🥗 Kolacja")
                    st.write(f"**{d['kolacja']['nazwa']}**")
                    st.caption(f"Składniki: {', '.join(d['kolacja']['skladniki'])}")
                    st.info(d['kolacja']['przepis'])

        st.markdown("---")
        st.subheader("🛒 Wygenerowana Zbiorcza Lista Zakupów")
        st.success(st.session_state.shared_shopping_list)
        st.info("💡 Lista została automatycznie zapisana. Możesz przejść do zakładki **🏷️ Lista zakupów z promocjami** lub **📊 Lista na podstawie wag**, aby natychmiast podzielić te zakupy na sklepy i sprawdzić budżet!")


# ==========================================
# MODUŁ 2: LISTA ZAKUPÓW Z PROMOCJAMI (LIDL & AUCHAN)
# ==========================================
elif menu_choice == "🏷️ Lista zakupów z promocjami":
    st.title("🏷️ Lista zakupów z promocjami (Lidl vs Auchan)")
    st.write("AI porównuje asortyment i oferty w sieciach Lidl oraz Auchan, wyznacza opłacalność i grupuje listę na sklepy.")

    budget_promotions = st.number_input("Twój budżet łączny (zł):", min_value=0.0, value=250.0, step=25.0, key="budget_promo")
    
    default_text = st.session_state.shared_shopping_list if st.session_state.shared_shopping_list else "chleb żytni na zakwasie, mleko owsiane, dojrzałe awokado, kawa ziarnista, świeża bazylia, pomidory malinowe, ser halloumi, pasta do zębów, oliwa z oliwek extra virgin, cytryny, hummus klasyczny, płatki owsiane górskie, jajka z wolnego wybiegu"
    
    raw_promotions = st.text_area(
        "Wpisz artykuły do kupienia (lub użyj listy z planera dań):",
        value=default_text,
        height=110,
        key="input_promo"
    )

    def analyze_promotions(items_list):
        client = genai.Client(api_key=API_KEY)
        prompt = f"""
        Przeanalizuj poniższe artykuły pod kątem cen, marek własnych i opłacalności w sieciach LIDL Polska oraz AUCHAN Polska:
        {', '.join(items_list)}

        Dla każdego produktu zwróć:
        1. "name": nazwa produktu
        2. "sklep": 'Lidl' lub 'Auchan' (bardziej opłacalny sklep)
        3. "cena_pln": szacowana cena w PLN
        4. "ocena_koszt": w skali 1-5 (5 = tani/przystępny)
        5. "ocena_potrzeba": w skali 1-5 (5 = pierwsza potrzeba/zdrowie)
        6. "ocena_okazja": w skali 1-5 (5 = bardzo korzystna cena/marka własna)
        7. "uwagi": krótkie uzasadnienie wyboru sklepu

        Zwróć WYŁĄCZNIE czysty JSON w postaci tablicy obiektów:
        [
          {{"name": "Masło", "sklep": "Lidl", "cena_pln": 6.29, "ocena_koszt": 4.0, "ocena_potrzeba": 5.0, "ocena_okazja": 4.0, "uwagi": "Tania marka własna Pilos"}}
        ]
        """
        raw = generate_with_fallback(client, prompt)
        match = re.search(r'\[\s*\{.*\}\s*\]', raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(raw.replace("```json", "").replace("
