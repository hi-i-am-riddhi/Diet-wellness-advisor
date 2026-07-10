"""
Diet & Wellness Advisor – Flask Backend
Integrates with IBM watsonx Orchestrate via REST API.
"""

import os
import json
import time
import logging
import requests
from pathlib import Path
from functools import lru_cache
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv

# ─── Load environment variables ───────────────────────────────────────────────
# Use the directory that contains app.py — works regardless of where Flask
# is launched from (e.g.  python app.py  OR  flask run  from parent dir).
_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env")

# ─── Flask app setup ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Orchestrate config ───────────────────────────────────────────────────────
ORCHESTRATE_INSTANCE_URL  = os.getenv("ORCHESTRATE_INSTANCE_URL", "").rstrip("/")
ORCHESTRATE_API_KEY        = os.getenv("ORCHESTRATE_API_KEY", "")
ORCHESTRATE_AGENT_ID       = os.getenv("ORCHESTRATE_AGENT_ID", "")
# "live" targets the published agent; "draft" targets the unpublished working copy.
# Override in .env if you have a custom environment UUID.
ORCHESTRATE_ENVIRONMENT_ID = os.getenv("ORCHESTRATE_ENVIRONMENT_ID", "live")
IAM_TOKEN_URL              = "https://iam.cloud.ibm.com/identity/token"

# ─────────────────────────────────────────────────────────────────────────────
#  AGENT_INSTRUCTIONS  – reference copy of the Orchestrate prompt.
#  Keep this in sync with your Orchestrate agent's system prompt.
# ─────────────────────────────────────────────────────────────────────────────
AGENT_INSTRUCTIONS = """
You are a Diet & Wellness Advisor AI assistant with specialized knowledge in
nutrition, preventive healthcare, and holistic well-being.

CORE RULES
──────────
1. KNOWLEDGE-BASE-ONLY ANSWERS
   Answer ONLY from the vetted knowledge base loaded into this agent.
   If a question is outside the knowledge base, reply:
   "I don't have verified information on that topic. Please consult a
    qualified healthcare professional."

2. DOCTOR DISCLAIMER (mandatory on every health response)
   Every response that touches symptoms, conditions, or treatments MUST
   end with:
   "⚕ This is general wellness information, not medical advice.
    Always consult a licensed doctor for diagnosis and treatment."

3. SYMPTOM-POSSIBILITY FRAMING
   When listing symptoms, always use hedged language:
   "may include", "can include", "some people experience".
   Never state symptoms as guaranteed or universal.

4. STRUCTURED RESPONSE FORMAT
   For condition/disease queries, respond in this exact structure:
   ## Overview
   [2-3 sentence overview]

   ## Symptoms
   - [symptom 1]
   - [symptom 2]

   ## Precautions
   - [precaution 1]
   - [precaution 2]

   ## Suggested Diet
   - [food/diet tip 1]
   - [food/diet tip 2]

   ## Note
   [doctor disclaimer]

5. DAILY PLANNER FORMAT
   When the user asks for a meal plan or daily planner, respond ONLY
   in this structure:
   ### Morning
   [meals / activities]

   ### Afternoon
   [meals / activities]

   ### Evening
   [meals / activities]

   ### Night
   [meals / activities]

   ### Notes
   [any dietary notes + doctor disclaimer]

6. MENTAL HEALTH CONDITIONS
   For mental health topics, avoid diagnostic language. Use:
   "Signs that someone may benefit from support include..."
   Always recommend professional mental health support.

7. SCOPE LIMITATION
   Do not provide:
   - Specific drug dosages or prescriptions
   - Emergency medical advice (redirect to emergency services)
   - Personalized lab result interpretation
"""

# ─────────────────────────────────────────────────────────────────────────────
#  DISEASE LIBRARY  – 35 conditions matching the Orchestrate knowledge base
# ─────────────────────────────────────────────────────────────────────────────
DISEASE_LIBRARY = [
    # ── Physical Health ──
    {
        "id": "diabetes",
        "name": "Diabetes (Type 2)",
        "category": "physical",
        "tags": ["metabolic", "chronic", "lifestyle"],
        "overview": "A chronic condition where the body doesn't use insulin properly, leading to high blood sugar levels.",
        "symptoms": ["Increased thirst", "Frequent urination", "Fatigue", "Blurred vision", "Slow-healing wounds", "Tingling in hands/feet"],
        "precautions": ["Monitor blood sugar regularly", "Maintain healthy weight", "Exercise at least 30 min/day", "Limit refined carbs and sugars", "Regular HbA1c checks"],
        "suggested_diet": ["Low-glycaemic index foods", "Whole grains (oats, quinoa, brown rice)", "Leafy greens", "Legumes and beans", "Healthy fats (avocado, olive oil)", "Avoid sugary drinks and processed foods"],
    },
    {
        "id": "hypertension",
        "name": "Hypertension (High Blood Pressure)",
        "category": "physical",
        "tags": ["cardiovascular", "chronic", "lifestyle"],
        "overview": "A condition where blood pressure in the arteries is persistently elevated, increasing risk of heart disease and stroke.",
        "symptoms": ["Often no symptoms (silent killer)", "Headaches", "Shortness of breath", "Nosebleeds", "Dizziness"],
        "precautions": ["Limit sodium to <2300 mg/day", "Exercise regularly", "Avoid smoking and excess alcohol", "Manage stress", "Monitor BP at home"],
        "suggested_diet": ["DASH diet (fruits, vegetables, low-fat dairy)", "Potassium-rich foods (bananas, sweet potatoes)", "Reduce salt intake", "Magnesium-rich foods (nuts, seeds)", "Avoid processed and fast foods"],
    },
    {
        "id": "obesity",
        "name": "Obesity",
        "category": "physical",
        "tags": ["metabolic", "lifestyle", "chronic"],
        "overview": "Excess body fat accumulation that presents a risk to health, typically defined as a BMI of 30 or higher.",
        "symptoms": ["Excess body weight", "Fatigue", "Joint pain", "Shortness of breath", "Increased sweating", "Sleep apnea"],
        "precautions": ["Caloric deficit diet", "Regular aerobic and strength exercise", "Behavioral therapy", "Reduce sedentary time", "Sleep 7-9 hours/night"],
        "suggested_diet": ["High-fibre vegetables and fruits", "Lean proteins (chicken, fish, legumes)", "Whole grains", "Avoid sugary beverages", "Mindful eating practices"],
    },
    {
        "id": "heart_disease",
        "name": "Coronary Heart Disease",
        "category": "physical",
        "tags": ["cardiovascular", "chronic"],
        "overview": "Narrowing of coronary arteries due to plaque build-up, reducing blood flow to the heart muscle.",
        "symptoms": ["Chest pain or pressure (angina)", "Shortness of breath", "Heart palpitations", "Fatigue", "Swelling in legs"],
        "precautions": ["Quit smoking", "Control cholesterol and blood pressure", "Regular cardiac check-ups", "Maintain healthy weight", "Manage diabetes if present"],
        "suggested_diet": ["Mediterranean diet", "Omega-3 rich fish (salmon, sardines)", "Nuts and seeds", "Olive oil", "Fruits and vegetables", "Limit saturated and trans fats"],
    },
    {
        "id": "asthma",
        "name": "Asthma",
        "category": "physical",
        "tags": ["respiratory", "chronic"],
        "overview": "A chronic respiratory condition causing airway inflammation and narrowing, leading to breathing difficulties.",
        "symptoms": ["Wheezing", "Shortness of breath", "Chest tightness", "Coughing (especially at night)", "Difficulty exercising"],
        "precautions": ["Identify and avoid triggers", "Use prescribed inhalers correctly", "Monitor peak flow", "Vaccinate against flu", "Keep indoor air clean"],
        "suggested_diet": ["Anti-inflammatory foods (berries, leafy greens)", "Vitamin D sources (salmon, fortified foods)", "Magnesium-rich foods", "Ginger and turmeric", "Avoid sulfites (dried fruit, wine)"],
    },
    {
        "id": "arthritis",
        "name": "Arthritis (Rheumatoid & Osteoarthritis)",
        "category": "physical",
        "tags": ["musculoskeletal", "chronic", "inflammatory"],
        "overview": "Inflammation and degeneration of joints causing pain, stiffness, and reduced mobility.",
        "symptoms": ["Joint pain", "Stiffness (morning stiffness >1 hr in RA)", "Swelling", "Decreased range of motion", "Fatigue"],
        "precautions": ["Low-impact exercise (swimming, yoga)", "Maintain healthy weight", "Physical therapy", "Use joint-protecting techniques", "Adequate rest"],
        "suggested_diet": ["Omega-3 fatty acids", "Cherries and berries (antioxidants)", "Olive oil", "Whole grains", "Avoid red meat and fried foods"],
    },
    {
        "id": "thyroid",
        "name": "Thyroid Disorders (Hypo/Hyperthyroidism)",
        "category": "physical",
        "tags": ["endocrine", "hormonal"],
        "overview": "Conditions where the thyroid gland produces too little (hypothyroidism) or too much (hyperthyroidism) thyroid hormone.",
        "symptoms": ["Fatigue or hyperactivity", "Weight gain or loss", "Hair thinning", "Temperature sensitivity", "Heart rate changes", "Mood changes"],
        "precautions": ["Regular thyroid function tests", "Take prescribed medication consistently", "Avoid iodine excess (hyperthyroidism)", "Manage stress", "Sleep adequately"],
        "suggested_diet": ["Iodine-rich foods for hypothyroid (seaweed, fish)", "Selenium (Brazil nuts, sunflower seeds)", "Zinc (pumpkin seeds, chickpeas)", "Avoid soy in excess for hypothyroid", "Anti-inflammatory diet"],
    },
    {
        "id": "anemia",
        "name": "Anemia (Iron-Deficiency)",
        "category": "physical",
        "tags": ["blood", "nutritional"],
        "overview": "A condition where the blood lacks enough healthy red blood cells, often due to iron deficiency.",
        "symptoms": ["Fatigue and weakness", "Pale skin", "Shortness of breath", "Dizziness", "Cold hands and feet", "Brittle nails"],
        "precautions": ["Iron supplementation as prescribed", "Vitamin C with iron-rich meals", "Avoid tea/coffee with meals", "Treat underlying causes", "Regular CBC blood tests"],
        "suggested_diet": ["Red meat and poultry", "Leafy greens (spinach, kale)", "Legumes (lentils, chickpeas)", "Fortified cereals", "Vitamin C foods (oranges, bell peppers)", "Pumpkin seeds and tofu"],
    },
    {
        "id": "kidney_disease",
        "name": "Chronic Kidney Disease",
        "category": "physical",
        "tags": ["renal", "chronic"],
        "overview": "Gradual loss of kidney function over time, affecting the body's ability to filter waste and fluids.",
        "symptoms": ["Fatigue", "Swelling in ankles/feet", "Decreased urine output", "Nausea", "Shortness of breath", "Confusion"],
        "precautions": ["Control blood pressure and diabetes", "Limit NSAIDs", "Stay hydrated", "Regular kidney function tests", "Low-protein diet as advised"],
        "suggested_diet": ["Low-potassium foods (apples, cabbage)", "Low-phosphorus diet", "Limited protein intake", "Low sodium", "White rice and bread over whole grain when phosphorus is high"],
    },
    {
        "id": "liver_disease",
        "name": "Fatty Liver Disease (NAFLD)",
        "category": "physical",
        "tags": ["hepatic", "metabolic", "lifestyle"],
        "overview": "Build-up of extra fat in liver cells, often linked to obesity, diabetes, or high cholesterol.",
        "symptoms": ["Usually no symptoms initially", "Fatigue", "Upper right abdominal discomfort", "Enlarged liver", "Elevated liver enzymes"],
        "precautions": ["Lose weight gradually", "Avoid alcohol", "Control blood sugar", "Exercise regularly", "Regular liver function tests"],
        "suggested_diet": ["Coffee (may protect liver)", "Leafy greens", "Omega-3 foods", "Olive oil", "Avoid alcohol, sugary drinks, processed foods"],
    },
    {
        "id": "osteoporosis",
        "name": "Osteoporosis",
        "category": "physical",
        "tags": ["bone", "nutritional", "ageing"],
        "overview": "A bone disease where decreased bone density increases the risk of fractures.",
        "symptoms": ["Often silent until fracture", "Back pain", "Stooped posture", "Loss of height", "Bone fractures from minor falls"],
        "precautions": ["Weight-bearing exercise", "Calcium and Vitamin D supplementation", "Avoid smoking and excess alcohol", "Fall prevention measures", "DEXA bone density scans"],
        "suggested_diet": ["Dairy products (milk, yogurt, cheese)", "Fortified plant milks", "Leafy greens (kale, bok choy)", "Sardines and salmon with bones", "Vitamin D from sunlight and supplements"],
    },
    {
        "id": "gout",
        "name": "Gout",
        "category": "physical",
        "tags": ["metabolic", "joint", "lifestyle"],
        "overview": "A type of arthritis caused by the build-up of uric acid crystals in joints, causing intense pain.",
        "symptoms": ["Sudden severe joint pain (often big toe)", "Redness and swelling", "Warmth in affected joint", "Limited movement", "Recurring attacks"],
        "precautions": ["Stay well hydrated", "Limit alcohol (especially beer)", "Maintain healthy weight", "Avoid prolonged fasting", "Take prescribed urate-lowering therapy"],
        "suggested_diet": ["Cherries and cherry juice", "Water (2-3L/day)", "Low-fat dairy", "Whole grains", "Avoid red meat, organ meats, shellfish, sugary drinks"],
    },
    {
        "id": "ibs",
        "name": "Irritable Bowel Syndrome (IBS)",
        "category": "physical",
        "tags": ["gastrointestinal", "chronic"],
        "overview": "A common disorder affecting the large intestine, causing cramping, bloating, and altered bowel habits.",
        "symptoms": ["Abdominal pain/cramping", "Bloating", "Gas", "Diarrhea or constipation (or alternating)", "Mucus in stool"],
        "precautions": ["Identify food triggers", "Manage stress", "Eat smaller, regular meals", "Stay hydrated", "Probiotic foods"],
        "suggested_diet": ["Low-FODMAP diet", "Cooked vegetables over raw", "Soluble fibre (oats, psyllium)", "Probiotic yogurt", "Avoid caffeine, alcohol, fried foods, artificial sweeteners"],
    },
    {
        "id": "celiac",
        "name": "Celiac Disease",
        "category": "physical",
        "tags": ["autoimmune", "gastrointestinal", "nutritional"],
        "overview": "An autoimmune disorder where ingestion of gluten causes damage to the small intestine.",
        "symptoms": ["Diarrhea", "Bloating and gas", "Fatigue", "Weight loss", "Skin rash (dermatitis herpetiformis)", "Anaemia", "Bone/joint pain"],
        "precautions": ["Strict gluten-free diet for life", "Read food labels carefully", "Avoid cross-contamination", "Bone density monitoring", "Nutritional supplementation"],
        "suggested_diet": ["Rice, quinoa, millet, corn", "Potatoes", "Fruits and vegetables", "Lean meats and fish", "Certified gluten-free oats (with caution)", "Avoid wheat, barley, rye"],
    },
    {
        "id": "migraine",
        "name": "Migraines",
        "category": "physical",
        "tags": ["neurological", "chronic"],
        "overview": "Recurring episodes of severe headache, often with nausea and sensitivity to light and sound.",
        "symptoms": ["Throbbing head pain (one side)", "Nausea and vomiting", "Sensitivity to light and sound", "Visual aura", "Fatigue"],
        "precautions": ["Identify and avoid triggers", "Regular sleep schedule", "Stress management", "Stay hydrated", "Limit caffeine"],
        "suggested_diet": ["Regular meals (avoid skipping)", "Magnesium-rich foods", "Hydrate well (2L+/day)", "Omega-3 foods", "Avoid tyramine foods (aged cheese, cured meats), alcohol, MSG"],
    },
    {
        "id": "pcod",
        "name": "PCOS/PCOD",
        "category": "physical",
        "tags": ["hormonal", "reproductive", "women's health"],
        "overview": "A hormonal disorder in women involving enlarged ovaries with small cysts, affecting menstrual cycles and fertility.",
        "symptoms": ["Irregular periods", "Excess androgen (facial hair, acne)", "Polycystic ovaries on ultrasound", "Weight gain", "Thinning hair"],
        "precautions": ["Maintain healthy weight", "Regular exercise", "Manage insulin resistance", "Regular gynaecological check-ups", "Stress management"],
        "suggested_diet": ["Low-GI carbohydrates", "High-fibre vegetables", "Lean protein", "Healthy fats (avocado, nuts)", "Anti-inflammatory spices (turmeric, cinnamon)", "Avoid refined carbs and sugary foods"],
    },
    {
        "id": "sleep_apnea",
        "name": "Sleep Apnea",
        "category": "physical",
        "tags": ["respiratory", "sleep", "lifestyle"],
        "overview": "A sleep disorder where breathing repeatedly stops and starts, often linked to obesity.",
        "symptoms": ["Loud snoring", "Gasping during sleep", "Excessive daytime sleepiness", "Morning headaches", "Difficulty concentrating"],
        "precautions": ["Use CPAP as prescribed", "Weight loss if overweight", "Sleep on side", "Avoid alcohol before bed", "Quit smoking"],
        "suggested_diet": ["Weight management diet", "Anti-inflammatory foods", "Avoid heavy meals before bedtime", "Limit alcohol", "Mediterranean-style diet"],
    },
    {
        "id": "eczema",
        "name": "Eczema (Atopic Dermatitis)",
        "category": "physical",
        "tags": ["skin", "inflammatory", "allergic"],
        "overview": "A chronic skin condition causing inflamed, itchy, and red skin patches, often flaring in response to triggers.",
        "symptoms": ["Dry, sensitive skin", "Intense itching", "Red or brownish-grey patches", "Scaly or crusty skin", "Oozing or crusting in severe cases"],
        "precautions": ["Moisturise regularly", "Identify food/environmental triggers", "Avoid harsh soaps", "Use prescribed topical treatments", "Manage stress"],
        "suggested_diet": ["Omega-3 foods (fatty fish, flaxseed)", "Probiotic foods (yogurt, kefir)", "Vitamin E foods (nuts, seeds)", "Anti-inflammatory diet", "Potential triggers to test: dairy, eggs, soy, wheat, nuts"],
    },
    # ── Mental Health ──
    {
        "id": "depression",
        "name": "Depression",
        "category": "mental",
        "tags": ["mental health", "mood", "chronic"],
        "overview": "A mood disorder causing persistent feelings of sadness, loss of interest, and reduced functioning in daily life.",
        "symptoms": ["Persistent sadness or emptiness", "Loss of interest in activities", "Fatigue", "Changes in appetite/weight", "Sleep disturbances", "Difficulty concentrating", "Feelings of worthlessness"],
        "precautions": ["Seek professional mental health support", "Maintain social connections", "Regular physical exercise", "Consistent sleep schedule", "Avoid alcohol and drugs"],
        "suggested_diet": ["Omega-3 fatty acids (linked to mood support)", "Tryptophan-rich foods (turkey, eggs, nuts)", "Probiotic foods (gut-brain axis)", "Dark chocolate (moderate)", "Leafy greens (folate)", "Avoid alcohol, excess caffeine, ultra-processed foods"],
    },
    {
        "id": "anxiety",
        "name": "Anxiety Disorders",
        "category": "mental",
        "tags": ["mental health", "mood", "chronic"],
        "overview": "A group of conditions characterised by excessive worry, fear, or nervousness that interferes with daily activities.",
        "symptoms": ["Excessive worry", "Restlessness or feeling on edge", "Fatigue", "Difficulty concentrating", "Muscle tension", "Sleep problems", "Panic attacks (in panic disorder)"],
        "precautions": ["Cognitive-behavioural therapy (CBT)", "Mindfulness and breathing exercises", "Limit caffeine and alcohol", "Regular exercise", "Adequate sleep"],
        "suggested_diet": ["Magnesium-rich foods (dark chocolate, nuts)", "Omega-3s", "Chamomile tea", "Whole grains (serotonin precursors)", "Probiotic foods", "Avoid caffeine, alcohol, artificial additives"],
    },
    {
        "id": "adhd",
        "name": "ADHD",
        "category": "mental",
        "tags": ["mental health", "neurodevelopmental"],
        "overview": "A neurodevelopmental disorder involving difficulty with attention, hyperactivity, and impulsivity.",
        "symptoms": ["Inattention", "Hyperactivity", "Impulsivity", "Disorganisation", "Forgetfulness", "Difficulty completing tasks"],
        "precautions": ["Structured daily routines", "Behavioural therapy", "Medication management as prescribed", "Exercise regularly", "Limit screen time and distractions"],
        "suggested_diet": ["Protein-rich breakfast", "Omega-3 fatty acids", "Iron and zinc foods", "Complex carbohydrates", "Regular meal times", "Avoid artificial colours, additives, excess sugar"],
    },
    {
        "id": "bipolar",
        "name": "Bipolar Disorder",
        "category": "mental",
        "tags": ["mental health", "mood"],
        "overview": "A mental health condition characterised by extreme mood swings including emotional highs (mania) and lows (depression).",
        "symptoms": ["Manic episodes (elevated mood, reduced sleep need)", "Depressive episodes", "Rapid mood changes", "Impulsive behaviour during mania", "Fatigue during depression"],
        "precautions": ["Consistent medication adherence", "Regular psychiatric follow-up", "Stable sleep schedule", "Avoid alcohol and recreational drugs", "Stress management"],
        "suggested_diet": ["Omega-3 fatty acids", "Regular meal schedule", "Whole foods", "Limit alcohol and caffeine", "Stay hydrated"],
    },
    {
        "id": "ocd",
        "name": "OCD (Obsessive-Compulsive Disorder)",
        "category": "mental",
        "tags": ["mental health", "anxiety"],
        "overview": "A disorder featuring unwanted repetitive thoughts (obsessions) and behaviours (compulsions) performed to reduce anxiety.",
        "symptoms": ["Intrusive, unwanted thoughts", "Repetitive behaviours (checking, counting, cleaning)", "Anxiety when rituals not performed", "Time-consuming rituals", "Avoidance of triggers"],
        "precautions": ["Exposure and Response Prevention (ERP) therapy", "Medication as prescribed (SSRIs)", "Support groups", "Stress reduction", "Regular therapy sessions"],
        "suggested_diet": ["Balanced, nutritious diet", "Omega-3s (anti-inflammatory)", "Probiotic foods", "Avoid excess caffeine (can worsen anxiety)", "Consistent meal schedule to support routine"],
    },
    {
        "id": "ptsd",
        "name": "PTSD (Post-Traumatic Stress Disorder)",
        "category": "mental",
        "tags": ["mental health", "trauma"],
        "overview": "A mental health condition triggered by experiencing or witnessing a terrifying event, causing lasting distress.",
        "symptoms": ["Flashbacks", "Nightmares", "Severe anxiety", "Avoidance of reminders", "Emotional numbness", "Hypervigilance", "Sleep disturbances"],
        "precautions": ["Trauma-focused CBT or EMDR therapy", "Safe support network", "Avoid alcohol/drugs as coping", "Grounding techniques", "Medication if prescribed"],
        "suggested_diet": ["Omega-3 fatty acids", "Magnesium-rich foods", "Probiotic foods (gut-brain link)", "Avoid alcohol and stimulants", "Regular meal schedule for stability"],
    },
    {
        "id": "eating_disorders",
        "name": "Eating Disorders (Anorexia / Bulimia / BED)",
        "category": "mental",
        "tags": ["mental health", "nutritional", "behavioural"],
        "overview": "Serious conditions affecting eating behaviours and thoughts about food, weight, and body image.",
        "symptoms": ["Restricted eating or extreme dieting", "Binge eating", "Purging behaviours", "Distorted body image", "Anxiety around food", "Nutritional deficiencies"],
        "precautions": ["Professional psychological and nutritional support", "Family-based therapy where appropriate", "Avoid diet culture messaging", "Regular medical monitoring", "Safe and supportive environment"],
        "suggested_diet": ["Individualized nutrition plan with a dietitian", "Regular structured meals", "No food restriction without medical supervision", "Adequate caloric intake", "Mindful eating practices"],
    },
    {
        "id": "insomnia",
        "name": "Insomnia",
        "category": "mental",
        "tags": ["mental health", "sleep", "lifestyle"],
        "overview": "Difficulty falling asleep, staying asleep, or getting restorative sleep, affecting daytime function.",
        "symptoms": ["Difficulty falling asleep", "Waking during the night", "Early morning awakening", "Daytime fatigue", "Difficulty concentrating", "Irritability"],
        "precautions": ["Sleep hygiene practices", "Consistent bedtime routine", "Limit screen time before bed", "CBT for insomnia (CBT-I)", "Limit caffeine after noon"],
        "suggested_diet": ["Tryptophan-rich foods (turkey, milk, banana)", "Magnesium foods (almonds, spinach)", "Chamomile tea", "Avoid caffeine after 2pm", "Avoid large meals and alcohol before bed"],
    },
    {
        "id": "burnout",
        "name": "Burnout",
        "category": "mental",
        "tags": ["mental health", "stress", "lifestyle"],
        "overview": "A state of chronic stress leading to physical and emotional exhaustion, cynicism, and a sense of ineffectiveness.",
        "symptoms": ["Chronic fatigue", "Cynicism", "Reduced performance", "Physical symptoms (headaches, GI issues)", "Emotional detachment", "Feeling helpless"],
        "precautions": ["Set work-life boundaries", "Take regular breaks", "Prioritise rest and recovery", "Seek support or counselling", "Identify and address root stressors"],
        "suggested_diet": ["Nutrient-dense whole foods", "Adaptogenic herbs (ashwagandha, rhodiola — consult doctor first)", "Hydration", "Omega-3s", "Limit alcohol and stimulants"],
    },
    {
        "id": "social_anxiety",
        "name": "Social Anxiety Disorder",
        "category": "mental",
        "tags": ["mental health", "anxiety"],
        "overview": "Intense fear of social situations due to worry about being negatively judged, embarrassed, or humiliated.",
        "symptoms": ["Fear of social situations", "Blushing, sweating, trembling", "Avoidance of social events", "Nausea in social settings", "Difficulty making eye contact"],
        "precautions": ["CBT therapy", "Gradual exposure to feared situations", "Social skills training", "Medication if severe (SSRIs)", "Mindfulness practices"],
        "suggested_diet": ["Magnesium-rich foods", "Omega-3s", "Limit caffeine (worsens anxiety symptoms)", "Probiotic foods", "Vitamin B complex foods"],
    },
    # ── Additional Physical ──
    {
        "id": "hypo_thyroid",
        "name": "Hypothyroidism",
        "category": "physical",
        "tags": ["endocrine", "hormonal", "women's health"],
        "overview": "Underactive thyroid producing insufficient thyroid hormone, slowing many of the body's functions.",
        "symptoms": ["Fatigue", "Weight gain", "Cold intolerance", "Constipation", "Dry skin and hair", "Slow heart rate", "Depression"],
        "precautions": ["Take levothyroxine as prescribed", "Regular TSH monitoring", "Avoid raw goitrogens in excess", "Take medication on empty stomach", "Check for drug interactions"],
        "suggested_diet": ["Iodine-rich foods (seaweed, fish)", "Selenium (Brazil nuts)", "Zinc (pumpkin seeds)", "Adequate protein", "Cook cruciferous vegetables before eating"],
    },
    {
        "id": "gastritis",
        "name": "Gastritis",
        "category": "physical",
        "tags": ["gastrointestinal", "inflammatory"],
        "overview": "Inflammation of the stomach lining, which may be acute or chronic, causing discomfort and digestive issues.",
        "symptoms": ["Stomach pain or burning", "Nausea and vomiting", "Feeling full quickly", "Bloating", "Loss of appetite", "Dark stools (if bleeding)"],
        "precautions": ["Avoid NSAIDs and alcohol", "H. pylori treatment if positive", "Small, frequent meals", "Quit smoking", "Manage stress"],
        "suggested_diet": ["Non-acidic fruits (bananas, melons)", "Lean proteins", "Probiotic yogurt", "Cooked vegetables", "Avoid spicy, acidic, fatty, and fried foods"],
    },
    {
        "id": "pcos_diet",
        "name": "PCOS – Diet Management",
        "category": "physical",
        "tags": ["hormonal", "nutritional", "women's health"],
        "overview": "Dietary strategies specifically tailored to manage symptoms of Polycystic Ovary Syndrome through nutrition.",
        "symptoms": ["Insulin resistance", "Weight gain around abdomen", "Cravings for carbs/sugar", "Hormonal imbalance symptoms"],
        "precautions": ["Work with a registered dietitian", "Balance macronutrients at each meal", "Consistent meal timing", "Regular physical activity", "Monitor blood sugar"],
        "suggested_diet": ["Anti-inflammatory foods", "Cinnamon (insulin sensitivity)", "Leafy greens", "High-fibre legumes", "Healthy fats", "Limit processed carbs, dairy if sensitive, excess soy"],
    },
    {
        "id": "acne",
        "name": "Acne (Dietary Triggers)",
        "category": "physical",
        "tags": ["skin", "hormonal", "lifestyle"],
        "overview": "A skin condition involving clogged pores causing pimples, often influenced by hormones and diet.",
        "symptoms": ["Blackheads and whiteheads", "Pimples", "Cysts", "Oily skin", "Scarring"],
        "precautions": ["Avoid touching face", "Gentle skincare routine", "Non-comedogenic products", "Manage stress", "Consult dermatologist for persistent acne"],
        "suggested_diet": ["Low-glycaemic diet", "Zinc foods (pumpkin seeds, legumes)", "Omega-3s (reduce inflammation)", "Green tea", "Avoid high-GI foods, dairy (some people), chocolate in excess"],
    },
    {
        "id": "cholesterol",
        "name": "High Cholesterol (Hyperlipidaemia)",
        "category": "physical",
        "tags": ["cardiovascular", "metabolic", "lifestyle"],
        "overview": "Elevated levels of cholesterol or triglycerides in the blood, increasing cardiovascular disease risk.",
        "symptoms": ["Usually no symptoms", "Xanthomas (fatty deposits under skin)", "Chest pain if arteries affected", "Discovered through blood test"],
        "precautions": ["Regular lipid panel tests", "Exercise 150+ min/week", "Quit smoking", "Medication (statins) if prescribed", "Weight management"],
        "suggested_diet": ["Soluble fibre (oats, barley, psyllium)", "Plant sterols (fortified foods)", "Fatty fish", "Nuts (especially walnuts)", "Olive oil", "Avoid trans fats, saturated fats, processed foods"],
    },
    {
        "id": "vitamin_d",
        "name": "Vitamin D Deficiency",
        "category": "physical",
        "tags": ["nutritional", "bone", "immune"],
        "overview": "Insufficient vitamin D, critical for bone health, immune function, and mood regulation.",
        "symptoms": ["Fatigue", "Bone pain", "Muscle weakness", "Frequent infections", "Depression", "Hair loss"],
        "precautions": ["Sunlight exposure 15-30 min/day", "Vitamin D3 supplementation", "Regular blood level monitoring", "Combine with Vitamin K2 and calcium", "Test 25(OH)D levels annually"],
        "suggested_diet": ["Fatty fish (salmon, tuna)", "Egg yolks", "Fortified foods (milk, cereal, OJ)", "Mushrooms (UV-exposed)", "Vitamin D3 supplement as recommended"],
    },
    {
        "id": "stroke_prevention",
        "name": "Stroke Prevention & Recovery Diet",
        "category": "physical",
        "tags": ["cardiovascular", "neurological", "prevention"],
        "overview": "Stroke occurs when blood supply to part of the brain is cut off. Diet plays a key role in prevention and post-stroke recovery.",
        "symptoms": ["Sudden face drooping (FAST)", "Arm weakness", "Speech difficulty", "Sudden severe headache", "Vision changes", "Balance loss"],
        "precautions": ["Control blood pressure (primary risk factor)", "Quit smoking", "Manage diabetes and cholesterol", "Anticoagulants if prescribed", "Regular cardiovascular check-ups", "Seek emergency care immediately for stroke symptoms (call 999/911)"],
        "suggested_diet": ["Mediterranean diet pattern", "DASH diet (proven to lower BP)", "High-potassium foods (bananas, leafy greens)", "Omega-3 fatty acids (salmon, sardines)", "Whole grains and legumes", "Limit salt, saturated fats, alcohol", "Antioxidant-rich fruits and vegetables"],
    },
]

# ─── IAM Token Cache ──────────────────────────────────────────────────────────
_token_cache = {"token": None, "expires_at": 0}

def get_iam_token() -> str:
    """Fetch and cache an IBM Cloud IAM Bearer token."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    # Guard: catch placeholder values that were never replaced
    placeholder_values = {"", "your_ibm_cloud_api_key_here", "your-api-key", "YOUR_API_KEY"}
    if ORCHESTRATE_API_KEY.strip() in placeholder_values:
        raise RuntimeError(
            "ORCHESTRATE_API_KEY is not set. "
            "Open your .env file and replace the placeholder with a real IBM Cloud IAM API key. "
            "Create one at: https://cloud.ibm.com/iam/apikeys"
        )

    try:
        resp = requests.post(
            IAM_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": ORCHESTRATE_API_KEY.strip(),
            },
            timeout=15,
        )
    except requests.Timeout:
        raise RuntimeError("IAM token request timed out. Check your network connection.")
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error reaching IBM IAM: {exc}")

    if resp.status_code != 200:
        logger.error("IAM token error: %s %s", resp.status_code, resp.text)
        # Parse the IBM error code for a human-readable message
        _iam_error_hint(resp)  # raises RuntimeError with friendly message

    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
    return _token_cache["token"]


def _iam_error_hint(resp: requests.Response) -> None:
    """Raise a clear RuntimeError with actionable guidance for common IAM failures."""
    status = resp.status_code
    try:
        body = resp.json()
        error_code = body.get("errorCode", "")
        error_msg  = body.get("errorMessage", resp.text[:200])
    except Exception:
        error_code = ""
        error_msg  = resp.text[:200]

    hints = {
        "BXNIM0415E": (
            "IBM Cloud API key not found (BXNIM0415E). "
            "The key in your .env may be deleted, belong to a different account, "
            "or contain extra spaces/quotes. "
            "Fix: go to https://cloud.ibm.com/iam/apikeys → create a new key → "
            "paste it (no quotes, no spaces) as ORCHESTRATE_API_KEY in your .env."
        ),
        "BXNIM0407E": (
            "API key is expired or revoked (BXNIM0407E). "
            "Create a new key at https://cloud.ibm.com/iam/apikeys and update .env."
        ),
        "BXNIM0106E": (
            "Malformed API key (BXNIM0106E). "
            "Check for accidental line breaks or truncation in your .env value."
        ),
    }

    if error_code in hints:
        raise RuntimeError(hints[error_code])

    # Generic fallback
    raise RuntimeError(
        f"IAM authentication failed (HTTP {status}, code: {error_code}): {error_msg}. "
        "Verify ORCHESTRATE_API_KEY in your .env file."
    )


def _consume_sse_stream(resp: requests.Response) -> tuple[str, str]:
    """
    Consume an SSE stream from the Orchestrate chat/completions endpoint.

    Returns (assembled_text, thread_id).

    The stream emits newline-delimited  "data: <JSON>"  lines.
    Two object types carry useful payload:
      • thread.message.delta    – incremental content tokens in choices[].delta.content
      • thread.message.completed – final assembled message in data.message.content[0].text
    We prefer the completed event's text when available (cleaner), and fall back to
    accumulating the deltas otherwise.
    """
    full_text   = ""
    thread_id   = ""
    delta_parts: list[str] = []

    for raw_line in resp.iter_lines():
        if not raw_line:
            continue
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line.startswith("data: "):
            continue
        data_str = line[6:].strip()
        if data_str == "[DONE]":
            break
        try:
            ev = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        # Capture thread_id from any event
        if not thread_id:
            thread_id = ev.get("thread_id", "")

        obj = ev.get("object", "")

        if obj == "thread.message.delta":
            for choice in ev.get("choices", []):
                content = choice.get("delta", {}).get("content", "")
                if content:
                    delta_parts.append(content)

        elif obj == "thread.message.completed":
            # Prefer the clean assembled text from the completed event
            try:
                content_blocks = ev["data"]["message"]["content"]
                texts = [b.get("text", "") for b in content_blocks if "text" in b]
                if texts:
                    full_text = "\n\n".join(t.strip() for t in texts if t.strip())
            except (KeyError, TypeError):
                pass

    # Fall back to accumulated deltas if the completed event had no text
    if not full_text and delta_parts:
        full_text = "".join(delta_parts)

    return full_text.strip() or "No response received from the agent.", thread_id


def send_to_orchestrate(user_message: str, thread_id: str = "") -> dict:
    """
    Send a message to the watsonx Orchestrate agent via the SSE chat/completions
    endpoint and return a response dict.

    Endpoint:  {ORCHESTRATE_INSTANCE_URL}/v1/orchestrate/{agent_id}/chat/completions
    Auth:      Bearer token from IBM Cloud IAM
    Streaming: SSE — assembled before returning so callers stay sync.

    Pass thread_id to continue an existing conversation thread.
    A new thread_id is returned in the response for the caller to store.
    """
    if not all([ORCHESTRATE_INSTANCE_URL, ORCHESTRATE_API_KEY, ORCHESTRATE_AGENT_ID]):
        return {
            "type": "error",
            "text": (
                "Orchestrate is not configured. "
                "Set ORCHESTRATE_INSTANCE_URL, ORCHESTRATE_API_KEY, and "
                "ORCHESTRATE_AGENT_ID in your .env file."
            ),
        }

    try:
        token = get_iam_token()
    except RuntimeError as exc:
        return {"type": "error", "text": str(exc)}

    url = (
        f"{ORCHESTRATE_INSTANCE_URL}"
        f"/v1/orchestrate/{ORCHESTRATE_AGENT_ID}/chat/completions"
    )

    payload: dict = {
        "messages": [{"role": "user", "content": user_message}],
        "environment_id": ORCHESTRATE_ENVIRONMENT_ID,
    }
    # Resume an existing thread so the agent retains conversation context
    if thread_id:
        payload["thread_id"] = thread_id

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload,
                             stream=True, timeout=60)

        if resp.status_code == 401:
            return {"type": "error", "text": "Authentication failed. Check your API key."}
        if resp.status_code == 429:
            return {"type": "error", "text": "Rate limit reached. Please wait a moment and try again."}
        if resp.status_code == 404:
            return {"type": "error", "text": "Agent not found. Check your ORCHESTRATE_AGENT_ID."}
        if resp.status_code not in (200, 201):
            return {
                "type": "error",
                "text": f"Orchestrate API error {resp.status_code}: {resp.text[:300]}",
            }

        response_text, new_thread_id = _consume_sse_stream(resp)
        return {
            "type": "success",
            "text": response_text,
            "thread_id": new_thread_id,
        }

    except requests.Timeout:
        return {"type": "error", "text": "Request timed out. The agent is taking too long to respond."}
    except requests.RequestException as exc:
        logger.error("Orchestrate request error: %s", exc)
        return {"type": "error", "text": f"Connection error: {str(exc)}"}


def create_orchestrate_session() -> str:
    """
    No-op for the new SSE endpoint — thread IDs are created automatically by
    Orchestrate on the first message. Returns an empty string as a sentinel.
    """
    return ""


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat")
def chat():
    return render_template("chat.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/diseases")
def diseases():
    categories = {
        "physical": [d for d in DISEASE_LIBRARY if d["category"] == "physical"],
        "mental": [d for d in DISEASE_LIBRARY if d["category"] == "mental"],
    }
    return render_template("diseases.html", categories=categories, diseases=DISEASE_LIBRARY)


@app.route("/disease/<disease_id>")
def disease_detail(disease_id):
    disease = next((d for d in DISEASE_LIBRARY if d["id"] == disease_id), None)
    if not disease:
        return render_template("404.html"), 404
    return render_template("disease_detail.html", disease=disease)


@app.route("/planner")
def planner():
    return render_template("planner.html")


# ─── API Endpoints ────────────────────────────────────────────────────────────

@app.route("/api/session", methods=["POST"])
def api_create_session():
    """
    Initialise the conversation.
    With the SSE endpoint thread IDs are minted by Orchestrate on the first
    message, so there's nothing to pre-create here — we just confirm readiness.
    """
    return jsonify({
        "status": "ready",
        "environment_id": ORCHESTRATE_ENVIRONMENT_ID,
        "thread_id": session.get("orchestrate_thread_id", ""),
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Send a message to the Orchestrate agent and return structured response."""
    body = request.get_json(silent=True) or {}
    user_message = (body.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    # Carry the thread_id across turns for conversation continuity
    thread_id = session.get("orchestrate_thread_id", "")
    result = send_to_orchestrate(user_message, thread_id)

    # Persist the thread_id returned by Orchestrate for the next turn
    if result.get("thread_id"):
        session["orchestrate_thread_id"] = result["thread_id"]

    return jsonify(result)


@app.route("/api/diseases", methods=["GET"])
def api_diseases():
    """Return the full disease library as JSON."""
    query = request.args.get("q", "").lower()
    category = request.args.get("category", "")
    results = DISEASE_LIBRARY

    if query:
        results = [
            d for d in results
            if query in d["name"].lower()
            or query in d["overview"].lower()
            or any(query in t for t in d["tags"])
        ]
    if category:
        results = [d for d in results if d["category"] == category]

    return jsonify(results)


@app.route("/api/disease/<disease_id>", methods=["GET"])
def api_disease_detail(disease_id):
    disease = next((d for d in DISEASE_LIBRARY if d["id"] == disease_id), None)
    if not disease:
        return jsonify({"error": "Not found"}), 404
    return jsonify(disease)


@app.route("/api/planner", methods=["POST"])
def api_planner():
    """Generate a daily meal plan via Orchestrate."""
    body = request.get_json(silent=True) or {}
    condition = (body.get("condition") or "general wellness").strip()
    goal = (body.get("goal") or "balanced nutrition").strip()

    prompt = (
        f"Create a daily meal planner for someone with {condition} "
        f"focusing on {goal}. Use the Morning/Afternoon/Evening/Night format."
    )

    # Planner uses a fresh thread each time (no prior context needed)
    result = send_to_orchestrate(prompt, thread_id="")
    return jsonify(result)


@app.route("/api/symptom-check", methods=["POST"])
def api_symptom_check():
    """Check symptoms via Orchestrate."""
    body = request.get_json(silent=True) or {}
    symptoms = (body.get("symptoms") or "").strip()

    if not symptoms:
        return jsonify({"error": "No symptoms provided"}), 400

    prompt = (
        f"The user reports these symptoms: {symptoms}. "
        "What conditions may be associated with these symptoms? "
        "Provide an overview, possible conditions, dietary tips, and precautions."
    )

    # Symptom check uses a fresh thread each time
    result = send_to_orchestrate(prompt, thread_id="")
    return jsonify(result)


@app.route("/api/health", methods=["GET"])
def api_health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "orchestrate_configured": bool(ORCHESTRATE_INSTANCE_URL and ORCHESTRATE_API_KEY and ORCHESTRATE_AGENT_ID),
    })


# ─── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)
