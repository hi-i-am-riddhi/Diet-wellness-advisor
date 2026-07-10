# 🌿 WellnessAI – AI-Powered Diet & Wellness Advisor

An intelligent diet and wellness web application powered by **IBM watsonx Orchestrate**.
It provides AI-driven dietary guidance, symptom awareness, personalised meal plans,
and a searchable library of 35 health conditions.

---

## ✨ Features

| Feature | Description |
|---|---|
| **AI Chat Advisor** | Sends user questions to an IBM watsonx Orchestrate agent and displays structured recipe-style answers |
| **Wellness Dashboard** | BMI calculator, hydration/exercise/sleep tracker, macro tracker, and plate guide |
| **Disease Library** | 35 physical + mental health conditions with symptoms, precautions, and diet tips |
| **Meal Planner** | AI-generated Morning/Afternoon/Evening/Night meal plans |
| **Symptom Checker** | Describe symptoms → AI returns possible associated conditions |
| **Dark Mode** | Full dark/light theme toggle, persisted in localStorage |
| **Responsive Design** | Bootstrap 5 + custom CSS, fully mobile-friendly |
| **Medical Disclaimer** | Persistent banner on every health page |

---

## 🗂️ Project Structure

```
diet-wellness-advisor/
├── app.py                   # Flask backend, Orchestrate integration, routes
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── .env                     # Your real credentials (NOT committed)
├── Procfile                 # For IBM Cloud / Heroku deployment
├── runtime.txt              # Python version pin
├── templates/
│   ├── base.html            # Shared layout, navbar, disclaimer banner, footer
│   ├── index.html           # Home page / hero
│   ├── chat.html            # Full chat UI with sidebar
│   ├── dashboard.html       # Wellness dashboard
│   ├── diseases.html        # Searchable disease library grid
│   ├── disease_detail.html  # Individual condition detail page
│   ├── planner.html         # Daily meal planner
│   └── 404.html             # Not-found page
└── static/
    ├── css/style.css        # All custom styles + dark mode
    └── js/app.js            # Dark mode, response parser, planner renderer
```

---

## 🔑 Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `ORCHESTRATE_INSTANCE_URL` | Your watsonx Orchestrate instance base URL |
| `ORCHESTRATE_API_KEY` | IBM Cloud IAM API Key |
| `ORCHESTRATE_AGENT_ID` | The Agent / Assistant ID from Orchestrate |
| `FLASK_SECRET_KEY` | Long random string for Flask sessions |
| `FLASK_ENV` | `development` or `production` |
| `PORT` | Port number (default `5000`) |

### How to find your Orchestrate credentials

1. **Instance URL**: In IBM Cloud → Resources → Your Watson Assistant/Orchestrate instance → Manage → Credentials → URL
2. **API Key**: IBM Cloud → Manage → Access (IAM) → API keys → Create
3. **Agent ID**: In Orchestrate workspace → Your agent → Settings → API details

---

## 🚀 Local Development

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
# 1. Navigate to the project directory
cd diet-wellness-advisor

# 2. Create a virtual environment
python -m venv venv

# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and fill in environment variables
cp .env.example .env
# Edit .env with your IBM watsonx credentials

# 5. Run the development server
python app.py
```

Visit `http://localhost:5000`

---

## ☁️ Deployment to IBM Cloud (Cloud Foundry)

### Step 1 – Install IBM Cloud CLI

```bash
# Download from: https://cloud.ibm.com/docs/cli
ibmcloud login
ibmcloud target --cf
```

### Step 2 – Create deployment files

Create `Procfile`:
```
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

Create `runtime.txt`:
```
python-3.11.x
```

Create `manifest.yml`:
```yaml
applications:
  - name: wellness-ai-advisor
    memory: 256M
    instances: 1
    buildpack: python_buildpack
    command: gunicorn app:app --bind 0.0.0.0:$PORT
    env:
      FLASK_ENV: production
      ORCHESTRATE_INSTANCE_URL: https://your-instance-url
      ORCHESTRATE_API_KEY: your-api-key
      ORCHESTRATE_AGENT_ID: your-agent-id
      FLASK_SECRET_KEY: your-secret-key
```

> ⚠️ Do NOT commit real credentials to `manifest.yml`. Use IBM Cloud environment variables instead (see Step 3).

### Step 3 – Set environment variables via CLI (recommended)

```bash
ibmcloud cf push wellness-ai-advisor --no-start
ibmcloud cf set-env wellness-ai-advisor ORCHESTRATE_INSTANCE_URL "https://your-url"
ibmcloud cf set-env wellness-ai-advisor ORCHESTRATE_API_KEY "your-key"
ibmcloud cf set-env wellness-ai-advisor ORCHESTRATE_AGENT_ID "your-id"
ibmcloud cf set-env wellness-ai-advisor FLASK_SECRET_KEY "random-long-string"
ibmcloud cf start wellness-ai-advisor
```

### Step 4 – Push and verify

```bash
ibmcloud cf push wellness-ai-advisor
ibmcloud cf logs wellness-ai-advisor --recent
```

---

## ☁️ Deployment to IBM Cloud (Code Engine — Container)

### Step 1 – Build and push Docker image

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
ENV PORT=8080
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080", "--workers", "2"]
```

```bash
docker build -t wellness-ai .
docker tag wellness-ai us.icr.io/YOUR_NAMESPACE/wellness-ai:latest
docker push us.icr.io/YOUR_NAMESPACE/wellness-ai:latest
```

### Step 2 – Deploy to Code Engine

```bash
ibmcloud ce application create \
  --name wellness-ai-advisor \
  --image us.icr.io/YOUR_NAMESPACE/wellness-ai:latest \
  --env ORCHESTRATE_INSTANCE_URL=https://your-url \
  --env ORCHESTRATE_API_KEY=your-key \
  --env ORCHESTRATE_AGENT_ID=your-id \
  --env FLASK_SECRET_KEY=random-string \
  --port 8080
```

---

## 🤖 IBM watsonx Orchestrate Agent Setup

The `AGENT_INSTRUCTIONS` constant in `app.py` contains a reference copy of the
agent's system prompt. Ensure your Orchestrate agent is configured with the same
rules:

1. **Knowledge-base-only answers** – no hallucination outside the knowledge base
2. **Doctor disclaimer** – appended on every health response
3. **Symptom-possibility framing** – uses "may include", never absolute
4. **Structured format** – Overview / Symptoms / Precautions / Suggested Diet / Note
5. **Daily Planner format** – Morning / Afternoon / Evening / Night / Notes

### Uploading the Knowledge Base

Upload the 35-condition content as a `.pdf` or `.txt` knowledge document in
Orchestrate's **Knowledge** section. Each condition should include the same fields
reflected in `DISEASE_LIBRARY` in `app.py`.

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Home page |
| `GET` | `/chat` | Chat interface |
| `GET` | `/dashboard` | Wellness dashboard |
| `GET` | `/diseases` | Disease library |
| `GET` | `/disease/<id>` | Condition detail |
| `GET` | `/planner` | Meal planner |
| `POST` | `/api/session` | Create Orchestrate session |
| `POST` | `/api/chat` | Send message to Orchestrate agent |
| `POST` | `/api/planner` | Generate meal plan via Orchestrate |
| `POST` | `/api/symptom-check` | Check symptoms via Orchestrate |
| `GET` | `/api/diseases` | JSON: disease library (supports `?q=` and `?category=`) |
| `GET` | `/api/disease/<id>` | JSON: single condition |
| `GET` | `/api/health` | Health check + config status |

---

## 🛡️ Security Notes

- Never commit `.env` to source control — add it to `.gitignore`
- Rotate your IBM Cloud API key if accidentally exposed
- Use IBM Cloud Secrets Manager or Key Protect for production deployments
- Enable HTTPS (Cloud Foundry and Code Engine provide this automatically)
- The Flask `secret_key` should be at least 32 random characters

---

## 📦 .gitignore Recommendation

```
.env
venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
*.egg-info/
dist/
build/
```

---

## ⚕️ Medical Disclaimer

> WellnessAI provides **general wellness and nutrition information only**.
> It does **not** constitute medical advice, diagnosis, or treatment.
> Always consult a qualified healthcare professional.

---

*Built with ❤️ using IBM watsonx Orchestrate + Python Flask*
