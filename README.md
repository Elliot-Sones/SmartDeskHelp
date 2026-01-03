

## 📦 For Users (Installation)
*Just want to use the app?*

1.  **Download**: Get the latest `.dmg` from the [Releases](https://github.com/not-manu/kel/releases) page.
2.  **Install**: Drag Kel to your Applications folder.
3.  **Run**: Launch the app.
    *   *Note: If you see "Unidentified Developer", Right-Click -> Open -> Open.*
4.  **Setup**:
    *   Press `Cmd+K` (or `Ctrl+K`) to open the sidebar.
    *   Go to Settings and enter your [OpenRouter API Key](https://openrouter.ai).
    *   **That's it!** The local AI model is already bundled inside the app.

---

## 🛠️ For Developers (Build form Source)
*Want to modify the code?*

### Prerequisites
- **Node.js** 18+
- **Python** 3.10+
- **pnpm** (`npm install -g pnpm`)
- **HuggingFace Account** (for one-time model download)

### 1. Setup
```bash
# Clone the repository
git clone https://github.com/not-manu/kel.git
cd kel

# Install Node dependencies
pnpm install

# Install Python dependencies (for the local router)
pip install -r python/requirements.txt
```

### 2. Download the Model (One-Time)
To keep the repo light, we don't commit the 600MB model files. You need to download them once.
You will need a [HuggingFace Token](https://huggingface.co/settings/tokens) with "Read" permissions.

```bash
# Run the download script
python3 scripts/download_model.py
```
*This will fetch `function-gemma-270m-it` into `resources/models/` so the app can bundle it.*

### 3. Run Development
You need two terminals open:

**Terminal 1: The App**
```bash
pnpm dev
```

**Terminal 2: The Router Server**
```bash
python3 python/function_gemma_server.py
```

### 4. Build for Production
To create the `.dmg` installer (which includes the model):

```bash
pnpm build:mac
```
The output file will be in `dist/`.

---