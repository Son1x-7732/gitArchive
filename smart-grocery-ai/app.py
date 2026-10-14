import streamlit as st
import pandas as pd
from llama_cpp import Llama
import os

# --- 1. Page Configuration ---
st.set_page_config(page_title="Smart Grocery Generator", page_icon="🛒")
st.title("🛒 Smart Grocery List Generator")
st.caption("Powered by Mistral-7B-Instruct-v0.2 (Local)")

# --- 2. Load the GGUF Model (Cached) ---
@st.cache_resource
def load_model():
    model_path = "mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    
    if not os.path.exists(model_path):
        return None

    return Llama(
        model_path=model_path,
        n_ctx=2048,
        n_threads=6, 
        verbose=False
    )

llm = load_model()

# --- 3. Smart Generation Function ---
def generate_grocery_list_ai(prompt, servings):
    # FIXED: Removed the leading '<s>' to stop the terminal warning
    # We use a strict system prompt to force CSV format
    # Added a small example inside the prompt to ensure perfect formatting
    
    sys_prompt = (
        "You are a strict grocery list assistant. "
        "Extract ingredients for the meal. "
        "Format EXACTLY as: - Item | Category | Quantity\n"
        "Example:\n"
        "- Rice | Grains | 500g\n"
        "- Chicken | Protein | 1kg\n"
        "Do NOT speak. Do NOT explain. Just list items."
    )
    
    user_prompt = f"Make a grocery list for: {prompt} ({servings} servings)."
    
    # Mistral's required format: [INST] System + User [/INST]
    full_prompt = f"[INST] {sys_prompt}\n{user_prompt} [/INST]"

    # Run Inference
    output = llm(
        full_prompt,
        max_tokens=512,  # Limit output length
        stop=["</s>"],   # Stop signal
        echo=False
    )
    
    return output['choices'][0]['text']

# --- 4. Parsing Logic (Robust) ---
def parse_ai_output(text):
    rows = []
    lines = text.strip().split("\n")
    
    for line in lines:
        # Clean up bullet points and extra spaces
        clean_line = line.replace("-", "").strip()
        
        # Skip empty lines or "Here is your list" chatty text
        if not clean_line or "|" not in clean_line:
            continue

        parts = [p.strip() for p in clean_line.split("|")]
        
        # Logic to handle missing data safely
        if len(parts) >= 3:
            rows.append(parts[:3]) # Perfect row: Item | Category | Qty
        elif len(parts) == 2:
            rows.append([parts[0], "General", parts[1]]) # Missing category -> Default to 'General'
            
    if not rows:
        return pd.DataFrame(columns=["Item", "Category", "Quantity"])

    return pd.DataFrame(rows, columns=["Item", "Category", "Quantity"])

# --- 5. UI Logic ---
if llm is None:
    st.error("❌ Model file not found!")
    st.warning("Please download 'mistral-7b-instruct-v0.2.Q4_K_M.gguf' and place it in this folder.")
    st.stop()

col1, col2 = st.columns([3, 1])
with col1:
    meal_input = st.text_input("What are you cooking?", placeholder="e.g., Chicken Biryani")
with col2:
    servings = st.number_input("Servings", min_value=1, value=2)

if st.button("Generate Grocery List"):
    if not meal_input.strip():
        st.warning("Please enter a meal.")
    else:
        with st.spinner("Mistral AI is thinking..."):
            try:
                # 1. Generate
                raw_text = generate_grocery_list_ai(meal_input, servings)
                
                # 2. Parse
                df = parse_ai_output(raw_text)
                
                if not df.empty:
                    st.success("List Generated Successfully!")
                    st.table(df)
                    
                    # CSV Download
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 Download CSV",
                        csv,
                        "grocery_list.csv",
                        "text/csv"
                    )
                else:
                    st.error("AI output was not in the correct format.")
                    st.text("Raw Output (Debug):")
                    st.code(raw_text)

            except Exception as e:
                st.error(f"Error: {e}")