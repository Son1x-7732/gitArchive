# Smart Grocery List Generator 🛒

A local AI-powered app that turns meal names into structured grocery lists using Mistral-7B.

## 📸 Demo
Here is the app in action:

![Main Interface](screenshots/1.png)

*Generating a list for Chicken Biryani:*
![Result Table](screenshots/2.png)

## Features
- 100% Offline & Private (Runs locally)
- Generates categorized ingredient lists
- Download list as CSV
- Powered by Mistral-7B-Instruct (GGUF)

## Setup
1. Clone the repo.
2. Install dependencies: `pip install -r requirements.txt`
3. **Download the Model:**
   - Download `mistral-7b-instruct-v0.2.Q4_K_M.gguf` from Hugging Face.
   - Place it in this folder.
4. Run the app: `streamlit run app.py`
