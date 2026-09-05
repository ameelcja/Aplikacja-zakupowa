import streamlit as st
import pandas as pd
import json
from google import genai

API_KEY = "AQ.Ab8RN6L7UO4NqURBJQJyKPIN9MXXiFKDqxgyn1PTcIqWE3hV5w"

st.set_page_config(page_title="Matryca Priorytetów Zakupowych", layout="centered")

st.title("🛒 Matryca Priorytetów Zakupowych")
st.write("Wpisz produkty, a AI dokona oceny punktowej (koszt, potrzeba, dostępność) i wyliczy priorytet na podstawie wag.")

# Skala / wagi kryteriów (zgodnie z tabelą)
st.sidebar.header("⚖️ Skala wagowa kryteriów")
waga_koszt = st.sidebar.number_input("Waga: Koszt", value=0.5, step=0.1)
waga_potrzeba = st.sidebar.number_input("Waga: Potrzeba", value=0.4, step=0.1)
waga_dostepnosc = st.sidebar.number_input("Waga: Dostępność", value=0.3, step=0.1)

budget = st.number_input("Twój budżet (zł):", min_value=0.0, value=500.0, step=50.0)

raw_input = st.text_area(
    "Lista zakupów:", 
    placeholder="np. telewizor, jajka, chleb, kurtka, laptop, karma dla psa, fotel, leki",
    height=110
)

def evaluate_items_with_ai(items_list):
    client = genai.Client(api_key=API_KEY)
    prompt = f"""
    Dla podanej listy produktów dokonaj oceny na rynku polskim:
    1. "cena_pln": szacowany realny koszt zakupu w PLN (liczba).
    2. "ocena_koszt": ocena w skali 1-5 pod kątem przystępności cenowej (5 = bardzo tani / drobny wydatek, 1 = bardzo wysoki koszt / drogi sprzęt).
    3. "ocena_potrzeba": ocena w skali 1-5 pod kątem konieczności życiowej (5 = absolutna konieczność, zdrowie, żywność podstawowa; 1 = luksus, zachcianka).
    4. "ocena_dostepnosc": ocena w skali 1-5 pod kątem pilności rynkowej (5 = trudnodostępny, rzadki, promocja czasowa; 1 = powszechny, dostępny od ręki w każdym markecie).

    Lista: {', '.join(items_list)}

    Zwróć WYŁĄCZNIE poprawny JSON (tablica obiektów) bez bloków markdown:
    [
      {{"name": "nazwa", "cena_pln": 5.5, "ocena_koszt": 5, "ocena_potrzeba": 5, "ocena_dostepnosc": 1}}
    ]
    """

    models_to_try = []
    try:
        for m in client.models.list():
            m_name = getattr(m, 'name', '')
            if 'flash' in m_name:
                models_to_try.append(m_name.replace('models/', ''))
    except Exception:
        pass

    if not models_to_try:
        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"Błąd modelu: {last_error}")

if st.button("Analizuj i ułóż plan zakupów"):
    if not raw_input.strip():
        st.warning("Wpisz przynajmniej jeden produkt.")
    else:
        items_raw = [x.strip() for x in raw_input.replace("\n", ",").split(",") if x.strip()]
        
        with st.spinner("AI ocenia parametry i wylicza priorytety..."):
            try:
                ai_data = evaluate_items_with_ai(items_raw)
                parsed_items = []

                for entry in ai_data:
                    cena = float(entry.get("cena_pln", 50.0))
                    pkt_koszt = float(entry.get("ocena_koszt", 3))
                    pkt_potrzeba = float(entry.get("ocena_potrzeba", 3))
                    pkt_dostepnosc = float(entry.get("ocena_dostepnosc", 1))

                    # Wzór zgodny ze skalą wagową: (koszt * 0.5) + (potrzeba * 0.4) + (dostępność * 0.3)
                    priorytet = round(
                        (pkt_koszt * waga_koszt) + 
                        (pkt_potrzeba * waga_potrzeba) + 
                        (pkt_dostepnosc * waga_dostepnosc), 
                        2
                    )

                    parsed_items.append({
                        "Nazwa produktu": entry.get("name", "").capitalize(),
                        "Szacowany koszt (zł)": cena,
                        "koszt": pkt_koszt,
                        "potrzeba": pkt_potrzeba,
                        "dostępność": pkt_dostepnosc,
                        "Priorytet": priorytet
                    })

                df = pd.DataFrame(parsed_items)
                df = df.sort_values(by="Priorytet", ascending=False).reset_index(drop=True)

                # Podział budżetu
                allocated = 0.0
                status = []
                for _, row in df.iterrows():
                    if allocated + row["Szacowany koszt (zł)"] <= budget:
                        allocated += row["Szacowany koszt (zł)"]
                        status.append("✅ Kup teraz")
                    else:
                        status.append("⏳ Odłóż")
                
                df["Decyzja"] = status

                st.subheader("Matryca priorytetów")
                st.dataframe(
                    df[["Nazwa produktu", "koszt", "potrzeba", "dostępność", "Priorytet", "Szacowany koszt (zł)", "Decyzja"]],
                    width="stretch"
                )

                col1, col2 = st.columns(2)
                col1.metric("Wykorzystany budżet", f"{allocated:.2f} zł")
                col2.metric("Pozostało środków", f"{budget - allocated:.2f} zł")
                
            except Exception as e:
                st.error(f"Błąd analizy: {e}")
