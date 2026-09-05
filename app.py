import streamlit as st
import pandas as pd
import json
import re
from google import genai
from google.genai import types

API_KEY = "AQ.Ab8RN6L7UO4NqURBJQJyKPIN9MXXiFKDqxgyn1PTcIqWE3hV5w"

st.set_page_config(page_title="Inteligentne Zakupy: Lidl vs Auchan", layout="wide")

st.title("🛒 Asystent Promocji: Lidl & Auchan")
st.write("Wpisz produkty, a AI przeszuka oferty w Lidlu oraz Auchan, przeliczy priorytety i rozdzieli listę na sklepy.")

# Wagi kryteriów
st.sidebar.header("⚖️ Skala wagowa kryteriów")
waga_koszt = st.sidebar.number_input("Waga: Koszt / Przystępność", value=0.5, step=0.1)
waga_potrzeba = st.sidebar.number_input("Waga: Potrzeba", value=0.4, step=0.1)
waga_dostepnosc = st.sidebar.number_input("Waga: Okazja / Promocja", value=0.3, step=0.1)

budget = st.number_input("Dostępny budżet łącznie (zł):", min_value=0.0, value=250.0, step=25.0)

raw_input = st.text_area(
    "Twoja lista zakupów:", 
    placeholder="np. chleb żytni, mleko owsiane, awokado, kawa ziarnista, bazylia, pomidory malinowe",
    height=100
)

def analyze_promotions_and_assign_shops(items_list):
    client = genai.Client(api_key=API_KEY)

    prompt = f"""
    Jesteś analitykiem zakupowym dla rynku polskiego.
    Przeanalizuj poniższe produkty pod kątem aktualnych ofert, gazetek i poziomu cen w sieciach LIDL Polska oraz AUCHAN Polska:
    {', '.join(items_list)}

    Dla każdego artykułu:
    1. "name": nazwa produktu
    2. "sklep": wybierz wyłącznie 'Lidl' lub 'Auchan' (wskaż sklep z korzystniejszą ceną, promocją lub lepszą ofertą dla tej kategorii)
    3. "cena_pln": szacunkowa cena w PLN (liczba, np. 6.49)
    4. "ocena_koszt": w skali 1-5 (5 = niski wydatek/tani artykuł, 1 = drogi artykuł)
    5. "ocena_potrzeba": w skali 1-5 (5 = artykuł niezbędny/zdrowotny/żywność podstawowa, 1 = zachcianka/luksus)
    6. "ocena_okazja": w skali 1-5 (5 = świetna oferta/promocja, 1 = cena standardowa)
    7. "uwagi": krótkie uzasadnienie (np. 'Niższa cena regularna w Auchan', 'Lepsza oferta marek własnych w Lidlu')

    Zwróć odpowiedź WYŁĄCZNIE jako surowy JSON w formacie tablicy:
    [
      {{"name": "Masło", "sklep": "Lidl", "cena_pln": 5.99, "ocena_koszt": 4.5, "ocena_potrzeba": 5.0, "ocena_okazja": 4.0, "uwagi": "Dobra oferta w Lidlu"}}
    ]
    """

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.2
    )

    # Używamy modelu wskazanego przez API
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=config
    )

    text = response.text.strip()
    match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    return json.loads(text.replace("```json", "").replace("```", "").strip())

if st.button("🔍 Sprawdź promocje i optymalizuj koszyki"):
    if not raw_input.strip():
        st.warning("Wpisz przynajmniej jeden produkt.")
    else:
        items_raw = [x.strip() for x in raw_input.replace("\n", ",").split(",") if x.strip()]
        
        with st.spinner("AI analizuje oferty w Lidlu i Auchan oraz przelicza priorytety..."):
            try:
                data = analyze_promotions_and_assign_shops(items_raw)
                parsed = []

                for entry in data:
                    cena = float(entry.get("cena_pln", 10.0))
                    pkt_k = float(entry.get("ocena_koszt", 3.0))
                    pkt_p = float(entry.get("ocena_potrzeba", 3.0))
                    pkt_o = float(entry.get("ocena_okazja", 2.0))

                    priorytet = round(
                        (pkt_k * waga_koszt) + (pkt_p * waga_potrzeba) + (pkt_o * waga_dostepnosc), 
                        2
                    )

                    parsed.append({
                        "Produkt": entry.get("name", "").capitalize(),
                        "Rekomendowany sklep": entry.get("sklep", "Lidl"),
                        "Cena (zł)": cena,
                        "koszt": pkt_k,
                        "potrzeba": pkt_p,
                        "dostępność/okazja": pkt_o,
                        "Priorytet": priorytet,
                        "Wskazówka": entry.get("uwagi", "")
                    })

                df = pd.DataFrame(parsed)
                df = df.sort_values(by="Priorytet", ascending=False).reset_index(drop=True)

                allocated = 0.0
                status = []
                for _, row in df.iterrows():
                    if allocated + row["Cena (zł)"] <= budget:
                        allocated += row["Cena (zł)"]
                        status.append("✅ Kup teraz")
                    else:
                        status.append("⏳ Odłóż")
                df["Decyzja"] = status

                st.subheader("📋 Matryca priorytetów i rekomendacje")
                st.dataframe(
                    df[["Produkt", "Rekomendowany sklep", "koszt", "potrzeba", "dostępność/okazja", "Priorytet", "Cena (zł)", "Wskazówka", "Decyzja"]],
                    width="stretch"
                )

                col1, col2 = st.columns(2)
                col1.metric("Wykorzystany budżet", f"{allocated:.2f} zł")
                col2.metric("Pozostało środków", f"{budget - allocated:.2f} zł")

                st.divider()

                st.subheader("🛒 Gotowe listy zakupów z podziałem na sklepy")
                col_lidl, col_auchan = st.columns(2)

                df_kupione = df[df["Decyzja"] == "✅ Kup teraz"]

                with col_lidl:
                    st.markdown("### 🟡🔵 Lidl")
                    lidl_items = df_kupione[df_kupione["Rekomendowany sklep"] == "Lidl"]
                    if not lidl_items.empty:
                        for _, r in lidl_items.iterrows():
                            st.write(f"- **{r['Produkt']}** ~ {r['Cena (zł)']:.2f} zł *({r['Wskazówka']})*")
                        st.caption(f"Suma w Lidlu: **{lidl_items['Cena (zł)'].sum():.2f} zł**")
                    else:
                        st.info("Brak rekomendowanych zakupów w Lidlu.")

                with col_auchan:
                    st.markdown("### 🔴🟢 Auchan")
                    auchan_items = df_kupione[df_kupione["Rekomendowany sklep"] == "Auchan"]
                    if not auchan_items.empty:
                        for _, r in auchan_items.iterrows():
                            st.write(f"- **{r['Produkt']}** ~ {r['Cena (zł)']:.2f} zł *({r['Wskazówka']})*")
                        st.caption(f"Suma w Auchan: **{auchan_items['Cena (zł)'].sum():.2f} zł**")
                    else:
                        st.info("Brak rekomendowanych zakupów w Auchan.")

                odlozone = df[df["Decyzja"] == "⏳ Odłóż"]
                if not odlozone.empty:
                    with st.expander("⏳ Produkty przekraczające budżet (odłożone)"):
                        for _, r in odlozone.iterrows():
                            st.write(f"- **{r['Produkt']}** ({r['Rekomendowany sklep']}) ~ {r['Cena (zł)']:.2f} zł (Priorytet: {r['Priorytet']})")

            except Exception as e:
                st.error(f"Błąd analizy: {e}")
