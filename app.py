from flask import Flask, request, render_template, redirect, url_for, session, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, auth as admin_auth
import os
import secrets
from urllib.parse import quote_plus
import traceback
from sqlalchemy import func
from sqlalchemy import extract
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import json
import math
from pathlib import Path


os.environ["TRANSFORMERS_NO_TF"] = "1"

# Initialize Flask app
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# ==================== Database Configuration ====================
DB_USER = 'postgres'
DB_PASSWORD = '261020'  # <-- REPLACE WITH YOUR PASSWORD
DB_HOST = 'localhost'
DB_PORT = '5432'
DB_NAME = 'postgres'

encoded_password = quote_plus(DB_PASSWORD)
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'postgresql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==================== Schemes JSON & Analytics Helpers ====================
# ---------- Load schemes JSON once ----------
with open("schemes.json", encoding="utf-8") as f:
    SCHEMES = json.load(f)

# ========== Load Semantic Embedding Model ==========
print("Loading sentence transformer model...")
model = SentenceTransformer("all-MiniLM-L6-v2")

EMBEDDING_CACHE_PATH = "scheme_embeddings.npy"

# ========== Generate or Load Embeddings ==========
if os.path.exists(EMBEDDING_CACHE_PATH):
    print("Loading cached scheme embeddings...")
    scheme_embeddings = np.load(EMBEDDING_CACHE_PATH)
else:
    print("Computing scheme embeddings...")
    scheme_texts = []
    for s in SCHEMES:
        text = " ".join([
            s.get("name", ""),
            s.get("category", ""),
            s.get("description", ""),
            s.get("benefits", "")
        ])
        scheme_texts.append(text)

    scheme_embeddings = model.encode(scheme_texts)
    scheme_embeddings = np.array(scheme_embeddings)

    print("Saving embeddings cache...")
    np.save(EMBEDDING_CACHE_PATH, scheme_embeddings)

print("Scheme embeddings ready:", scheme_embeddings.shape)

# -----------------------
# Strict / Soft Eligibility
# -----------------------
def scheme_strict_matches_user(scheme, user):
    """
    Return True if user meets strict eligibility requirements declared in scheme.
    Checks (if present in scheme): state, min_age, max_age, eligible_genders,
    eligible_occupations, income limits, eligible_caste/category, disability, marital status.
    If scheme does not declare a field, that field is not enforced.
    """
    # State
    user_state = (getattr(user, "state", "") or "").strip().lower()
    states = [s.lower() for s in (scheme.get("beneficiary_states") or [])]
    if states:
        if "all india" not in states and user_state not in states:
            return False

    # Age
    user_age = getattr(user, "age", None)
    min_age = scheme.get("min_age")
    max_age = scheme.get("max_age")
    if user_age is not None:
        if min_age is not None and user_age < min_age:
            return False
        if max_age is not None and user_age > max_age:
            return False

    # Gender
    user_gender = (getattr(user, "gender", "") or "").strip()
    allowed_genders = scheme.get("eligible_genders") or scheme.get("eligible_gender")
    if allowed_genders:
        allowed = [g.strip().lower() for g in allowed_genders] if isinstance(allowed_genders, (list,tuple)) else [allowed_genders.strip().lower()]
        if user_gender and user_gender.lower() not in allowed:
            return False

    # Occupation
    user_occ = (getattr(user, "occupation", "") or "").strip().lower()
    allowed_occs = scheme.get("eligible_occupations") or scheme.get("eligible_occupation")
    if allowed_occs:
        allowed = [o.strip().lower() for o in allowed_occs] if isinstance(allowed_occs, (list,tuple)) else [allowed_occs.strip().lower()]
        if user_occ and user_occ not in allowed:
            return False

    # Income limits (try multiple possible key names)
    user_monthly_income = float(getattr(user, "monthly_income", 0) or 0)
    user_annual_income = float(getattr(user, "annual_income", user_monthly_income * 12) or 0)
    max_income_keys = ["income_limit", "max_income", "annual_income_limit", "income_ceiling"]
    for k in max_income_keys:
        if k in scheme and scheme[k] is not None:
            try:
                lim = float(scheme[k])
                # assume scheme value is annual if > 10000, otherwise treat as monthly (?) – handle conservatively:
                if lim > 10000:
                    if user_annual_income > lim:
                        return False
                else:
                    # if small number, check monthly
                    if user_monthly_income > lim:
                        return False
            except Exception:
                pass

    # Caste / category / social group eligibility
    user_caste = (getattr(user, "caste", "") or "").strip().lower()
    eligible_categories = scheme.get("eligible_categories") or scheme.get("eligible_castes") or scheme.get("eligible_caste")
    if eligible_categories:
        allowed = [c.strip().lower() for c in eligible_categories] if isinstance(eligible_categories, (list,tuple)) else [eligible_categories.strip().lower()]
        if user_caste and user_caste not in allowed:
            return False

    # Disability / special groups
    user_disability = getattr(user, "is_disabled", False) or getattr(user, "disability", False)
    eligible_disabilities = scheme.get("eligible_disabilities") or scheme.get("requires_disability")
    if eligible_disabilities:
        # if scheme requires disability and user doesn't have it -> fail
        if isinstance(eligible_disabilities, bool):
            if eligible_disabilities and not user_disability:
                return False
        else:
            # if list of categories
            if not user_disability:
                return False

    # Marital status
    user_marital = (getattr(user, "marital_status", "") or "").strip().lower()
    eligible_marital = scheme.get("eligible_marital_status")
    if eligible_marital:
        allowed = [m.strip().lower() for m in eligible_marital] if isinstance(eligible_marital, (list,tuple)) else [eligible_marital.strip().lower()]
        if user_marital and user_marital not in allowed:
            return False

    # If no strict rule failed, pass
    return True


def scheme_soft_matches_user(scheme, user):
    """
    Return True if user partially matches the scheme (soft match).
    Soft match = scheme is not strict-eligible but the user matches at least one of:
    state, occupation, gender, age range (near), or income within a reasonable band.
    """
    # If strict match, it's not "soft" here (we'll compute only for non-strict)
    if scheme_strict_matches_user(scheme, user):
        return False

    # Build easy checks
    user_state = (getattr(user, "state", "") or "").strip().lower()
    states = [s.lower() for s in (scheme.get("beneficiary_states") or [])]

    user_occ = (getattr(user, "occupation", "") or "").strip().lower()
    allowed_occs = [o.lower() for o in (scheme.get("eligible_occupations") or [])] if scheme.get("eligible_occupations") else []

    user_gender = (getattr(user, "gender", "") or "").strip().lower()
    allowed_genders = [g.lower() for g in (scheme.get("eligible_genders") or [])] if scheme.get("eligible_genders") else []

    user_age = getattr(user, "age", None)
    min_age = scheme.get("min_age")
    max_age = scheme.get("max_age")

    # Conditions that count as soft match (any one true -> soft)
    conds = []

    # State match (soft)
    if states and user_state and user_state in states:
        conds.append(True)

    # occupation match (soft)
    if allowed_occs and user_occ and user_occ in allowed_occs:
        conds.append(True)

    # gender match (soft)
    if allowed_genders and user_gender and user_gender in allowed_genders:
        conds.append(True)

    # age within +/- 5 years of required range
    if user_age is not None and (min_age is not None or max_age is not None):
        low = min_age if min_age is not None else (user_age - 5)
        high = max_age if max_age is not None else (user_age + 5)
        if (user_age >= (low - 5)) and (user_age <= (high + 5)):
            conds.append(True)

    # income within reasonable band if scheme defines a limit
    user_monthly_income = float(getattr(user, "monthly_income", 0) or 0)
    user_annual_income = float(getattr(user, "annual_income", user_monthly_income * 12) or 0)
    for k in ["income_limit", "max_income", "annual_income_limit", "income_ceiling"]:
        if k in scheme and scheme[k] is not None:
            try:
                lim = float(scheme[k])
                # treat large numbers as annual
                if lim > 10000:
                    if user_annual_income <= lim * 1.2:  # allow 20% slack
                        conds.append(True)
                else:
                    if user_monthly_income <= lim * 1.2:
                        conds.append(True)
            except Exception:
                pass

    # If any soft condition true -> soft match
    return any(conds)

# ==========================================================
# HYBRID SEMANTIC + RULE-BASED RECOMMENDER  (FINAL VERSION)
# ==========================================================

# ---- Allowed Categories for Each Goal ----
GOAL_ALLOWED_CATEGORIES = {
    "buy two-wheeler": ["transport", "vehicle", "msme", "business", "infrastructure"],
    "farm equipment": ["agriculture", "farmer", "rural", "irrigation", "msme"],
    "business expansion": ["business", "entrepreneurship", "msme", "industry"],
    "child education": ["education", "school", "scholarship", "child welfare"],
    "solar panel": ["solar", "renewable", "energy", "agriculture", "irrigation"],
    "shop renovation": ["business", "entrepreneurship", "msme", "infrastructure", "urban"],
    "water pump": ["agriculture", "irrigation", "farmer", "rural"],
    "gold purchase": ["investment", "finance", "banking"],
    "skill development": ["skill", "training", "employment", "entrepreneurship"],
    "loan repayment": ["finance", "credit", "banking", "insurance"],
    "business setup": ["business", "entrepreneurship", "msme", "industry"],
    "kitchen appliances": ["women welfare", "housing", "lpg"],
    "festival expenses": ["welfare", "finance"],
    "wedding expenses": ["marriage", "women welfare", "child welfare"],
    "medical emergency": ["health", "medical", "insurance"],
    "school fees": ["education", "scholarship", "school", "child welfare"],
    "buy car": ["transport", "vehicle", "msme"],
    "emergency fund": ["insurance", "welfare", "finance"],
    "home repair": ["housing", "construction", "infrastructure", "urban", "home"],
    "vehicle repair": ["transport", "vehicle", "driver welfare"],
    "buy house": ["housing", "urban", "construction", "infrastructure"],
    "buy land": ["housing", "urban", "construction", "property", "investment"],
    "daughter marriage": ["women welfare", "marriage", "child welfare"],
    "new mobile phone": ["electronics", "digital", "technology"],
    "buy tractor": ["agriculture", "farmer", "rural", "irrigation"],
    "home decoration": ["housing", "home", "urban", "construction"],
    "laptop purchase": ["education", "digital", "technology", "student"],
    "build house": ["housing", "construction", "urban development"],
    "vacation trip": ["tourism", "travel", "welfare"],
    "retirement fund": ["pension", "senior citizen", "insurance", "welfare", "finance"],
    "furniture": ["housing", "home", "urban"],
    "gadget upgrade": ["digital", "technology"],
    "entertainment budget": ["culture", "sports", "arts"],
    "child higher education": ["education", "scholarship", "student"],
    "new clothes": ["women welfare", "child welfare", "welfare"],
    "property investment": ["investment", "finance", "housing", "property"],
    "pilgrimage trip": ["tourism", "welfare", "religion"],
    "garden development": ["agriculture", "urban development", "environment"],
    "home theater": ["digital", "technology", "entertainment"],
    "investment portfolio": ["investment", "banking", "finance", "insurance"],
}

def scheme_domain_matches_goal(goal_text, scheme):
    goal_key = goal_text.lower().strip()

    allowed_categories = GOAL_ALLOWED_CATEGORIES.get(goal_key, [])
    if not allowed_categories:
        return True  # fallback to avoid over-filtering

    allowed = [c.lower() for c in allowed_categories]

    # Extract scheme fields
    scheme_cat = (scheme.get("category") or "").lower()
    scheme_tags = [t.lower() for t in (scheme.get("tags") or [])]
    desc = (scheme.get("description") or "").lower()

    # L1: category match
    if any(ac in scheme_cat for ac in allowed):
        return True

    # L2: tags match
    if any(ac in tag for ac in allowed for tag in scheme_tags):
        return True

    # L3: description keyword match
    if any(ac in desc for ac in allowed):
        return True

    return False

# ----------------------------------------------------------
# RECOMMENDER FUNCTION
# ----------------------------------------------------------
def recommend_schemes_for_goal(user, goal, top_n=5, soft_top_n=5):
    """
    Balanced recommender (Option B).
    Returns two lists:
      - strict_top: schemes the user is strictly eligible for (ranked)
      - soft_top: relevant schemes the user can explore (not strictly eligible)
    Each returned scheme is a dict copied from SCHEMES with added keys:
      - score (float)
      - recommend_reason (string)
      - remaining_amount, months_without_scheme, months_with_scheme (estimates)
    """

    # --- Tunable thresholds / weights ---
    STRICT_SIM_THRESHOLD = 0.38   # min semantic similarity for strict candidates
    SOFT_SIM_THRESHOLD = 0.24     # min semantic similarity for soft candidates
    KEYWORD_BOOST_PER_HIT = 0.05
    OCCUPATION_BOOST = 0.12
    OCCUPATION_BOOST_SOFT = 0.06
    GENDER_BOOST = 0.12
    GENDER_BOOST_SOFT = 0.06
    AGE_BOOST = 0.12
    AGE_BOOST_SOFT = 0.06
    AFFORDABILITY_BASE = 0.25
    AFFORDABILITY_BASE_SOFT = 0.12

    # Normalise goal/user text
    goal_text = (goal.goal_name or "").strip().lower()
    if not goal_text:
        goal_text = ""

    # Embedding for the goal (vector)
    goal_embedding = model.encode([goal_text])
    similarity_scores = cosine_similarity(goal_embedding, scheme_embeddings)[0]

    # Personalization inputs
    income = float(getattr(user, "monthly_income", 0) or 0)
    expenses = float(getattr(user, "monthly_expenses", 0) or 0)
    surplus = income - expenses
    remaining = float(getattr(goal, "target_amount", 0) or 0) - float(getattr(goal, "saved_amount", 0) or 0)
    remaining = max(0.0, remaining)

    strict_results = []
    soft_results = []

    # small goal-specific keywords map (expand as needed)
    goal_kw_map = {
        "buy two-wheeler": ["ev", "electric", "vehicle", "bike", "scooter", "two-wheeler"],
        "home decoration": ["repair", "renovation", "paint", "interior", "furniture"],
        "medical emergency": ["health", "medical", "insurance", "treatment"],
        "child education": ["school", "scholarship", "tuition", "student"],
        "buy car": ["car", "four wheeler", "vehicle", "loan"],
    }
    goal_kws = goal_kw_map.get(goal_text, ["subsidy", "benefit", "loan", "grant", "support"])

    for idx, s in enumerate(SCHEMES):
        # --- Domain/category filter (avoid big irrelevant categories early) ---
        if not scheme_domain_matches_goal(goal_text, s):
            # skip completely — prevents agriculture showing for "buy two-wheeler", etc.
            continue

        # user eligibility checks
        is_strict = scheme_strict_matches_user(s, user)
        is_soft = False
        if not is_strict:
            is_soft = scheme_soft_matches_user(s, user)

        # If neither strict nor soft, we still might consider a soft semantic-only suggestion
        # only if it passes semantic threshold AND category is relevant.
        # For balanced B, we allow soft semantic candidates only if scheme_domain_matches_goal passed.

        # semantic score
        semantic_score = float(similarity_scores[idx])

        # discard very low semantic candidates (reduce noise)
        if semantic_score < SOFT_SIM_THRESHOLD:
            # Even soft suggestions must clear minimal semantic relevance
            continue

        # build a searchable text blob for keyword checks
        scheme_text = " ".join([
            s.get("name", ""),
            s.get("category", ""),
            s.get("description", "") or "",
            s.get("benefits", "") or "",
            " ".join(s.get("tags") or [])
        ]).lower()

        # keyword boosting
        keyword_hits = [kw for kw in goal_kws if kw in scheme_text]
        keyword_boost = KEYWORD_BOOST_PER_HIT * len(keyword_hits)

        # occupation boost (if user occupation matches scheme eligible occupations)
        user_occ = (getattr(user, "occupation", "") or "").strip().lower()
        allowed_occs = [o.lower() for o in (s.get("eligible_occupations") or [])] if s.get("eligible_occupations") else []
        occ_boost = 0.0
        if user_occ and user_occ in allowed_occs:
            occ_boost = OCCUPATION_BOOST if is_strict else OCCUPATION_BOOST_SOFT

        # gender boost
        user_gender = (getattr(user, "gender", "") or "").strip().lower()
        gender_boost = 0.0
        allowed_genders_raw = s.get("eligible_genders") or s.get("eligible_gender") or []
        allowed_genders = [g.lower() for g in allowed_genders_raw] if allowed_genders_raw else []
        if user_gender == "female" and any(w in scheme_text for w in ["women", "girl", "female"]):
            gender_boost = GENDER_BOOST if is_strict else GENDER_BOOST_SOFT

        # age boost
        age_boost = 0.0
        user_age = getattr(user, "age", None)
        min_age = s.get("min_age")
        max_age = s.get("max_age")
        if user_age is not None:
            if user_age >= 60 and any(x in scheme_text for x in ["pension", "senior"]):
                age_boost = AGE_BOOST if is_strict else AGE_BOOST_SOFT
            elif user_age <= 25 and any(x in scheme_text for x in ["skill", "education", "student"]):
                age_boost = (AGE_BOOST if is_strict else AGE_BOOST_SOFT) * 0.8

        # affordability boost (smaller when soft)
        afford_boost = 0.0
        if surplus > 0 and any(w in scheme_text for w in ["subsidy", "interest", "benefit", "grant", "loan"]):
            afford_boost = (AFFORDABILITY_BASE / max(surplus, 1.0)) * (1.0 if is_strict else 0.5)
            # clamp small values so they don't dominate
            afford_boost = min(afford_boost, 0.2)

        # final raw score
        final_score = semantic_score + keyword_boost + occ_boost + gender_boost + age_boost + afford_boost

        # Build reason string (useful for UI)
        reason_parts = [f"Semantic: {semantic_score:.2f}"]
        if keyword_hits:
            reason_parts.append(f"Keywords: {keyword_hits}")
        if occ_boost:
            reason_parts.append(f"OccBoost: {occ_boost:.2f}")
        if gender_boost:
            reason_parts.append(f"GenderBoost: {gender_boost:.2f}")
        if age_boost:
            reason_parts.append(f"AgeBoost: {age_boost:.2f}")
        if afford_boost:
            reason_parts.append(f"AffordBoost: {afford_boost:.2f}")
        reason_parts.append("Eligibility: " + ("Strict" if is_strict else ("Soft" if is_soft else "Semantic-only")))
        recommend_reason = " | ".join(reason_parts)

        # If scheme is strict-eligible, require a slightly higher semantic threshold
        if is_strict:
            if semantic_score < STRICT_SIM_THRESHOLD and final_score < (STRICT_SIM_THRESHOLD + 0.06):
                # even if strict eligible, require reasonable semantic match
                continue
            # push into strict list
            s_copy = dict(s)
            s_copy.update({
                "index": idx,
                "score": round(final_score, 4),
                "recommend_reason": recommend_reason,
                "remaining_amount": remaining,
            })
            # estimate months
            est_months_without_scheme = None
            est_months_with_scheme = None
            if surplus > 0 and remaining > 0:
                est_months_without_scheme = math.ceil(remaining / surplus)
                est_months_with_scheme = est_months_without_scheme  # Placeholder; optionally reduce if scheme provides a quantifiable benefit
            s_copy["months_without_scheme"] = est_months_without_scheme
            s_copy["months_with_scheme"] = est_months_with_scheme

            strict_results.append((final_score, s_copy))
            continue

        # For non-strict (soft) candidates: ensure semantic threshold & domain match
        # soft candidate accepted only if semantic >= SOFT_SIM_THRESHOLD
        if semantic_score >= SOFT_SIM_THRESHOLD:
            s_copy = dict(s)
            s_copy.update({
                "index": idx,
                "score": round(final_score, 4),
                "recommend_reason": recommend_reason + " (Soft)",
                "remaining_amount": remaining,
            })
            est_months_without_scheme = None
            est_months_with_scheme = None
            if surplus > 0 and remaining > 0:
                est_months_without_scheme = math.ceil(remaining / surplus)
                est_months_with_scheme = est_months_without_scheme
            s_copy["months_without_scheme"] = est_months_without_scheme
            s_copy["months_with_scheme"] = est_months_with_scheme

            soft_results.append((final_score, s_copy))

    # rank and return top lists
    strict_results.sort(key=lambda x: x[0], reverse=True)
    soft_results.sort(key=lambda x: x[0], reverse=True)

    strict_top = [r[1] for r in strict_results[:top_n]]
    soft_top = [r[1] for r in soft_results[:soft_top_n]]

    return strict_top, soft_top


def compute_health_and_savings(user):
    income = float(user.monthly_income or 0)
    expenses = float(user.monthly_expenses or 0)
    savings = income - expenses

    savings_rate = (savings / income * 100) if income > 0 else 0
    expense_ratio = (expenses / income * 100) if income > 0 else 0

    sr = max(0, min(100, savings_rate))
    er = max(0, min(100, expense_ratio))
    D = 1 if getattr(user, "has_loans", False) else 0

    health_score = 0.5 * sr + 0.3 * (100 - er) - 20 * D
    health_score = max(0, min(100, health_score))
    return round(health_score, 1), round(savings_rate, 1), round(expense_ratio, 1), income, expenses, savings

def estimate_months_to_goal(user, goal):
    income = float(user.monthly_income or 0)
    expenses = float(user.monthly_expenses or 0)
    surplus = income - expenses
    remaining = float(goal.target_amount or 0) - float(goal.saved_amount or 0)

    if surplus <= 0 or remaining <= 0:
        return None
    return math.ceil(remaining / surplus)

# ==================== Firebase Initialization ====================
# Initialize Firebase Admin SDK
print("\n" + "="*50)
print("INITIALIZING FIREBASE ADMIN SDK")
print("="*50)
try:
    # Check if file exists
    cred_path = 'secrets/moneypathai-firebase-adminsdk-fbsvc-b0e83e98d5.json'
    if os.path.exists(cred_path):
        print(f"✓ Credentials file found: {cred_path}")
        file_size = os.path.getsize(cred_path)
        print(f"  File size: {file_size} bytes")
    else:
        print(f"✗ Credentials file NOT FOUND: {cred_path}")
        print(f"  Current directory: {os.getcwd()}")
        print(f"  Files in secrets/: {os.listdir('secrets') if os.path.exists('secrets') else 'secrets/ not found'}")
    
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    print("✓ FIREBASE ADMIN SDK INITIALIZED SUCCESSFULLY!")
    print("="*50 + "\n")
except ValueError as e:
    # Might already be initialized
    print(f"⚠ Firebase already initialized or value error: {e}")
except Exception as e:
    print(f"✗ FIREBASE INITIALIZATION ERROR:")
    print(f"  Error type: {type(e).__name__}")
    print(f"  Error message: {e}")
    import traceback
    traceback.print_exc()
    print("="*50 + "\n")

# ==================== Knowledge Sources ====================
BASE_DIR = Path(__file__).resolve().parent
SCHEMES_PATH = BASE_DIR / "schemes.json"
RBI_TEXT_PATH = BASE_DIR / "Literacy Content RBI.txt"  # text extracted from txt

SCHEMES_DATA = []
RBI_SECTIONS = []

def load_schemes_data():
    global SCHEMES_DATA
    try:
        if SCHEMES_PATH.exists():
            with open(SCHEMES_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # New format: raw is a list of flat scheme dicts
            if isinstance(raw, list):
                SCHEMES_DATA = raw
            else:
                # fallback if you ever change structure again
                SCHEMES_DATA = raw.get("data", {}).get("hits", {}).get("items", [])
            print(f"Loaded {len(SCHEMES_DATA)} scheme records.")
        else:
            print("schemes.json not found.")
            SCHEMES_DATA = []
    except Exception as e:
        print("Error loading schemes.json:", e)
        SCHEMES_DATA = []


def load_rbi_text():
    global RBI_SECTIONS
    try:
        if RBI_TEXT_PATH.exists():
            text = RBI_TEXT_PATH.read_text(encoding="utf-8")
            RBI_SECTIONS = [s.strip() for s in text.split("\n\n") if len(s.strip()) > 150]
            print(f"Loaded {len(RBI_SECTIONS)} RBI text chunks.")
        else:
            print("Literacy-Content-RBI.txt not found.")
            RBI_SECTIONS = []
    except Exception as e:
        print("Error loading RBI text:", e)
        RBI_SECTIONS = []

load_schemes_data()
load_rbi_text()

# ==================== Database Models ====================
class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    firebase_uid = db.Column(db.String(128), unique=True, nullable=False)
    phone_number = db.Column(db.String(15), unique=True, index=True)
    
    # Basic Profile
    name = db.Column(db.String(100))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))  # male/female/other
    marital_status = db.Column(db.String(20))  # single/married/other
    
    # Education & Occupation
    education_level = db.Column(db.String(50))  # below_10th, 10th_12th, graduate, etc.
    occupation = db.Column(db.String(100))
    sector = db.Column(db.String(50))  # agriculture, services, manufacturing, etc.
    
    # Household & Location
    household_size = db.Column(db.Integer)
    state = db.Column(db.String(50))
    city = db.Column(db.String(100))
    location_type = db.Column(db.String(20))  # rural, semi-urban, urban
    location = db.Column(db.String(200))
    
    # Financials
    monthly_income = db.Column(db.Numeric)
    monthly_expenses = db.Column(db.Numeric)
    income_source_primary = db.Column(db.String(50))  # salary, farming, business, etc.
    has_irregular_income = db.Column(db.Boolean, default=False)
    has_loans = db.Column(db.Boolean, default=False)
    total_loan_amount = db.Column(db.Numeric)
    loan_type_primary = db.Column(db.String(50))
    monthly_emi_total = db.Column(db.Numeric)
    existing_loans = db.Column(db.Text)
    
    # Preferences
    preferred_payment_mode = db.Column(db.String(20))  # UPI, cash, card, wallet
    financial_literacy_level = db.Column(db.String(20))  # low, medium, high
    risk_tolerance = db.Column(db.String(20))  # low, medium, high
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade='all, delete-orphan')
    goals = db.relationship('Goal', backref='user', lazy=True, cascade='all, delete-orphan')



class Transaction(db.Model):
    __tablename__ = 'transactions'
    transaction_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric, nullable=False)
    type = db.Column(db.String(10), nullable=False)  # Income or Expense
    category = db.Column(db.String(50))
    mode_of_payment = db.Column(db.String(20))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Goal(db.Model):
    __tablename__ = 'goals'
    goal_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    goal_name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Numeric, nullable=False)
    saved_amount = db.Column(db.Numeric, default=0)
    start_date = db.Column(db.Date)
    deadline = db.Column(db.Date)
    goal_type = db.Column(db.String(20))  # Short-term or Long-term
    priority = db.Column(db.String(10))  # High, Medium, Low
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ==================== Helper Functions ====================
# ==================== Knowledge Helper Functions ====================

def text_to_vec(s):
    # very simple bag‑of‑words
    words = [w for w in s.lower().split() if len(w) > 2]
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq

def cosine_sim(a, b):
    if not a or not b:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    num = sum(a[w] * b[w] for w in common)
    denom1 = math.sqrt(sum(v*v for v in a.values()))
    denom2 = math.sqrt(sum(v*v for v in b.values()))
    return num / denom1 / denom2 if denom1 and denom2 else 0.0

def text_to_vec(s):
    # very simple bag‑of‑words
    words = [w for w in s.lower().split() if len(w) > 2]
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq

def cosine_sim(a, b):
    if not a or not b:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    num = sum(a[w] * b[w] for w in common)
    denom1 = math.sqrt(sum(v*v for v in a.values()))
    denom2 = math.sqrt(sum(v*v for v in b.values()))
    return num / denom1 / denom2 if denom1 and denom2 else 0.0

def text_to_vec(s):
    # very simple bag‑of‑words
    words = [w for w in s.lower().split() if len(w) > 2]
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq

def cosine_sim(a, b):
    if not a or not b:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    num = sum(a[w] * b[w] for w in common)
    denom1 = math.sqrt(sum(v*v for v in a.values()))
    denom2 = math.sqrt(sum(v*v for v in b.values()))
    return num / denom1 / denom2 if denom1 and denom2 else 0.0

def text_to_vec(s):
    # very simple bag‑of‑words
    words = [w for w in s.lower().split() if len(w) > 2]
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq

def cosine_sim(a, b):
    if not a or not b:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    num = sum(a[w] * b[w] for w in common)
    denom1 = math.sqrt(sum(v*v for v in a.values()))
    denom2 = math.sqrt(sum(v*v for v in b.values()))
    return num / denom1 / denom2 if denom1 and denom2 else 0.0

def find_relevant_rbi_chunks(message, max_chunks=3):
    if not RBI_SECTIONS:
        return []
    q_vec = text_to_vec(message)
    scored = []
    for chunk in RBI_SECTIONS:
        c_vec = text_to_vec(chunk)
        score = cosine_sim(q_vec, c_vec)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [c for _, c in scored[:max_chunks]]



def summarize_rbi_chunks(chunks, lang="en"):
    """Return RBI text chunks directly (lightly trimmed), without hard‑coded topics."""
    if not chunks:
        return ""
    # Join the best-matching chunks from RBI_SECTIONS
    text = "\n\n".join(chunks)
    # Optional: cap very long answers
    return text

def find_matching_schemes_for_question(message, base_filters=None, max_items=5):
    if not SCHEMES_DATA:
        return []
    msg = message.lower()
    results = []

    for scheme in SCHEMES_DATA:
        name = (scheme.get("name") or "").lower()
        category = (scheme.get("category") or "").lower()
        description = (scheme.get("description") or "").lower()
        tags = [t.lower() for t in (scheme.get("tags") or [])]
        beneficiary_states = [s.lower() for s in (scheme.get("beneficiary_states") or [])]

        score = 0

        # 1) Name similarity (data‑driven)
        if name:
            name_tokens = [t for t in name.replace('"', '').replace('-', ' ').split() if len(t) > 2]
            overlap = sum(1 for t in name_tokens if t in msg)
            if overlap >= 4:
                score += 10
            elif overlap == 3:
                score += 7
            elif overlap >= 1:
                score += 4

        # 2) Tags and category
        for t in tags:
            if t in msg:
                score += 2
        for c in category.split(','):
            c = c.strip()
            if c and c.lower() in msg:
                score += 2

        # 3) Description keywords
        if "insurance" in msg and "insurance" in description:
            score += 3
        if "health" in msg and "health" in description:
            score += 2
        if "loan" in msg and "loan" in description:
            score += 2
        if "pension" in msg and "pension" in description:
            score += 2

        # 4) Personalisation by state (if you pass base_filters later)
        if base_filters:
            user_state = (base_filters.get("state") or "").lower()
            if user_state and any(user_state in s or s == "all india" for s in beneficiary_states):
                score += 1

        if score > 0:
            results.append((score, scheme))

    results.sort(reverse=True, key=lambda x: x[0])
    return [s for _, s in results[:max_items]]



def format_scheme_list(schemes, lang="en", personalized=False):
    if not schemes:
        return ""
    lines = []
    
    for s in schemes:
        name = s.get("name", "Scheme")
        category = s.get("category", "")
        brief = s.get("description", "")
        if lang == "hi":
            lines.append(f"• {name} – श्रेणी: {category}. संक्षेप: {brief}") 
        else:
            lines.append(f"• {name} – Category: {category}. In brief: {brief}")  
    if lang == "hi":
        header = "आपके प्रश्न से मिलती हुई योजनाएँ:\n" if not personalized else "आपकी प्रोफ़ाइल के अनुसार उपयुक्त योजनाएँ:\n"
    else:
        header = "Schemes related to your question:\n" if not personalized else "Schemes that fit your profile:\n"
    return header + "\n".join(lines)

import math

def text_to_vec(s):
    words = [w for w in s.lower().split() if len(w) > 2]
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq

def cosine_sim(a, b):
    if not a or not b:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    num = sum(a[w] * b[w] for w in common)
    denom1 = math.sqrt(sum(v*v for v in a.values()))
    denom2 = math.sqrt(sum(v*v for v in b.values()))
    return num / denom1 / denom2 if denom1 and denom2 else 0.0

def find_relevant_rbi_chunks(message, max_chunks=3):
    if not RBI_SECTIONS:
        return []
    q_vec = text_to_vec(message)
    scored = []
    for chunk in RBI_SECTIONS:
        c_vec = text_to_vec(chunk)
        score = cosine_sim(q_vec, c_vec)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [c for _, c in scored[:max_chunks]]

def summarize_rbi_chunks(chunks, lang="en"):
    if not chunks:
        return ""
    text = "\n\n".join(chunks)
    return text

def generate_guest_response(message, lang='en'):
    msg = message.lower()
    rbi_chunks = find_relevant_rbi_chunks(message)
    rbi_part = summarize_rbi_chunks(rbi_chunks, lang) if rbi_chunks else ""
    print("DEBUG RBI chunks:", len(rbi_chunks))
    print("DEBUG RBI part empty?:", not bool(rbi_part))


    schemes_part = ""
    if any(k in msg for k in [
        "scheme", "schemes", "yojana", "योजना",
        "subsidy", "pension", "insurance",
        "farmer", "किसान", "student", "scholarship",
        "health", "loan", "mudra", "pm ", "pradhan mantri",
        "government scheme", "govt scheme"
    ]):
        generic_schemes = find_matching_schemes_for_question(message, base_filters=None, max_items=5)
        print("DEBUG schemes:", len(generic_schemes))
        if generic_schemes:
            # if only one strong match, show full content
            if len(generic_schemes) == 1:
                schemes_part = format_scheme_full(generic_schemes[0], lang)
            else:
                schemes_part = format_scheme_list(generic_schemes, lang, personalized=False)
        else:
            if lang == "hi":
                schemes_part = (
                    "फिलहाल इस सवाल के लिए कोई सटीक सरकारी योजना नहीं मिल रही है, "
                    "लेकिन नज़दीकी बैंक, पोस्ट ऑफिस या CSC केंद्र में वे आपकी पात्रता की जाँच कर सकते हैं।"
                )
            else:
                schemes_part = (
                    "Right now I cannot find a specific matching government scheme, "
                    "but your nearest bank, post office or CSC centre can check your detailed eligibility."
                )

    if lang == "hi":
        intro = "मैं आपके प्रश्न के आधार पर सामान्य जानकारी दे रहा हूँ।\n"
        tail = "\n\nअधिक व्यक्तिगत सलाह और सटीक पात्रता जाँच के लिए आप साइन अप कर सकते हैं।"
        fallback = "अभी मैं केवल सामान्य वित्तीय मार्गदर्शन दे सकता हूँ, कृपया अपना सवाल थोड़ा विस्तार से लिखें।"
    else:
        intro = "Here is general information based on your question.\n"
        tail = "\n\nYou can sign up to get personalised advice and exact eligibility checks."
        fallback = "Right now I can give only general guidance. Please describe your question in a bit more detail."

    # ---------- UPDATED OVERRIDES ----------
    if not rbi_part and not schemes_part and "scheme" not in msg and "yojana" not in msg and "योजना" not in msg:
        # simple canned answers for very generic questions
        if any(k in msg for k in ["income", "what is income", "आय"]):
            if lang == "hi":
                return (
                    "आय (Income) वह पैसा है जो आपको वेतन, मज़दूरी, खेती या व्यवसाय से मिलता है। "
                    "इसी आय से ज़रूरी खर्च पूरे होते हैं और जो बचता है वही आपकी बचत बनती है।"
                )
            else:
                return (
                    "Income is the money you receive from sources like salary, wages, farming or business. "
                    "You use it for essential expenses and whatever remains should be saved for emergencies and future goals."
                )

        if any(k in msg for k in ["banking", "bank account", "bank ", "खाता", "बैंकिंग"]):
            if lang == "hi":
                return (
                    "बैंकिंग का मतलब है बैंक खाते के माध्यम से पैसा सुरक्षित रखना, ब्याज कमाना और सेवाएँ "
                    "जैसे जमा, निकासी, पैसे भेजना और सरकारी लाभ सीधे खाते में लेना।"
                )
            else:
                return (
                    "Banking means using a bank account to keep money safe, earn interest and use services like "
                    "deposits, withdrawals, remittances and direct credit of government benefits."
                )

        if "save more money" in msg or "saving more" in msg or "अधिक पैसे बचा" in msg:
            if lang == "hi":
                return (
                    "ज्यादा बचत के लिए पहले 1–2 महीने अपना खर्च लिखें, फिर गैर‑ज़रूरी मदों में 10–15% कटौती करें। "
                    "आय का कम से कम 20% अलग खाते या आरडी/पीपीएफ में ऑटो‑डेबिट से डालें और उसे खर्च न करें।"
                )
            else:
                return (
                    "To save more, track your spending for 1–2 months and cut 10–15% from non‑essential items. "
                    "Move at least 20% of your income by auto‑transfer into a separate savings, RD or PPF account."
                )

        if "what government schemes am i eligible" in msg or "eligible for schemes" in msg:
            generic_schemes = find_matching_schemes_for_question(message, base_filters=None, max_items=5)
            if generic_schemes:
                return format_scheme_list(generic_schemes, lang, personalized=False)
            if lang == "hi":
                return (
                    "आपकी सही पात्रता जानने के लिए राज्य, आयु, लिंग और आय जैसी जानकारी ज़रूरी है। "
                    "सामान्य तौर पर किसान, छात्र, महिला, वरिष्ठ नागरिक और कम आय वाले परिवारों के लिए कई योजनाएँ हैं "
                    "जिन्हें नज़दीकी बैंक या CSC केंद्र पर विस्तार से देखा जा सकता है।"
                )
            else:
                return (
                    "To know exact eligibility the system needs your state, age, gender and income. "
                    "In general there are schemes for farmers, students, women, senior citizens and low‑income families, "
                    "which can be checked in detail at your nearest bank or CSC centre."
                )

        if "how to create a budget" in msg or ("budget" in msg and "how" in msg):
            if lang == "hi":
                return (
                    "बजट बनाने के लिए पहले हर महीने की कुल आय लिखें, फिर खर्चों को ज़रूरी और गैर‑ज़रूरी में बाँटें। "
                    "ज़रूरी खर्च (किराया, राशन, EMI) को लगभग 50–60%, बचत को कम से कम 20% और बाकी 20–30% को वैकल्पिक खर्च रखें।"
                )
            else:
                return (
                    "To create a budget, list total monthly income and then split expenses into essential and non‑essential. "
                    "Keep essentials around 50–60%, savings at least 20% and only 20–30% for lifestyle spending."
                )

        if any(k in msg for k in ["how to start investing", "how to start investment",
                                  "invest money", "investment", "investing", "निवेश"]):
            if lang == "hi":
                return (
                    "निवेश शुरू करने से पहले 3–6 महीने के खर्च जितना आपातकालीन फंड बचत खाते/एफडी में रखें और ऊँचे ब्याज वाला कर्ज घटाएँ। "
                    "फिर छोटे‑छोटे SIP के ज़रिए कम‑जोखिम विकल्प (RD, PPF, इंडेक्स फंड) से शुरुआत करें और हर महीने नियमित निवेश करें।"
                )
            else:
                return (
                    "Before you start investing, build an emergency fund of 3–6 months’ expenses and reduce high‑interest debt. "
                    "Then begin with small monthly SIPs into safer options like RD, PPF or index mutual funds and stay regular."
                )

        return fallback
    # ---------- END UPDATED OVERRIDES ----------

    parts = [intro]
    if rbi_part:
        parts.append(rbi_part)
    if schemes_part:
        parts.append("\n" + schemes_part)
    parts.append(tail)
    return "\n".join(parts)

def generate_ai_response(message, user, lang='en'):
    """
    Logged‑in users: RBI + schemes info + personalised metrics & recommendations.
    """
    message_lower = message.lower()

    base_rbi_chunks = find_relevant_rbi_chunks(message)
    base_rbi_part = summarize_rbi_chunks(base_rbi_chunks, lang) if base_rbi_chunks else ""
    base_scheme_part = ""
    if any(k in message_lower for k in [
        "scheme", "schemes", "yojana", "योजना",
        "subsidy", "pension", "insurance",
        "farmer", "किसान", "student", "scholarship",
        "health", "loan", "mudra", "pm ", "pradhan mantri",
        "government scheme", "govt scheme"
    ]):
        generic_schemes = find_matching_schemes_for_question(message, base_filters=None, max_items=3)
        if generic_schemes:
            if len(generic_schemes) == 1:
                # Single strong match → show full content
                base_scheme_part = format_scheme_full(generic_schemes[0], lang)
            else:
                # Multiple matches → keep brief list
                base_scheme_part = format_scheme_list(generic_schemes, lang, personalized=False)


    monthly_income = float(user.monthly_income) if user.monthly_income else 0
    monthly_expenses = float(user.monthly_expenses) if user.monthly_expenses else 0
    savings = monthly_income - monthly_expenses
    savings_rate = (savings / monthly_income * 100) if monthly_income > 0 else 0

    personalized_blocks = []

    if lang == 'hi':
        if any(k in message_lower for k in [
            "scheme", "schemes", "yojana", "योजना",
            "subsidy", "pension", "insurance",
            "farmer", "किसान", "student", "scholarship",
            "health", "loan", "mudra", "pm ", "pradhan mantri",
            "government scheme", "govt scheme"
        ]):
            scheme_text = recommend_schemes_for_user(user, message, lang)
            if not scheme_text:
                scheme_text = (
                    "अभी आपकी प्रोफ़ाइल के लिए कोई बिल्कुल सटीक योजना नहीं मिल रही, "
                    "लेकिन नज़दीकी बैंक या CSC पर वे और विस्तार से जाँच कर सकते हैं।"
                )
            personalized_blocks.append(scheme_text)

        if 'बचत' in message or 'save' in message_lower or 'saving' in message_lower:
            personalized_blocks.append(
                f"आपकी मासिक आय लगभग ₹{monthly_income:.0f} और खर्च ₹{monthly_expenses:.0f} हैं, "
                f"यानि आप लगभग ₹{savings:.0f} ({savings_rate:.1f}%) बचत कर रहे हैं.\n"
                "आपके लिए सुझाव:\n"
                "1) हर महीने निश्चित राशि को ऑटो‑डेबिट से बचत/आरडी/पीपीएफ में भेजें.\n"
                "2) जिन श्रेणियों में खर्च ज़्यादा है, वहाँ 10–15% कटौती का लक्ष्य रखें."
            )

        if 'लक्ष्य' in message or 'goal' in message_lower:
            goals = Goal.query.filter_by(user_id=user.user_id).all()
            if goals:
                goal_info = []
                for g in goals[:3]:
                    progress = (float(g.saved_amount) / float(g.target_amount) * 100) if g.target_amount else 0
                    goal_info.append(f"• {g.goal_name}: ₹{g.saved_amount}/{g.target_amount} ({progress:.0f}%)")
                personalized_blocks.append(
                    "आपके मौजूदा वित्तीय लक्ष्य:\n" + "\n".join(goal_info) +
                    "\n\nहर लक्ष्य के लिए अलग छोटी SIP या RD रखना आपके लिए बेहतर रहेगा."
                )

        if not personalized_blocks:
            personalized_blocks.append(
                f"आपकी प्रोफ़ाइल (आय ₹{monthly_income:.0f}, खर्च ₹{monthly_expenses:.0f}, स्थान {user.location}) के आधार पर, "
                "नियमित बचत और सही योजनाएँ चुनने से आपका वित्तीय स्वास्थ्य मज़बूत हो सकता है."
            )

    else:
        if any(k in message_lower for k in [
            "scheme", "schemes", "yojana", "योजना",
            "subsidy", "pension", "insurance",
            "farmer", "किसान", "student", "scholarship",
            "health", "loan", "mudra", "pm ", "pradhan mantri",
            "government scheme", "govt scheme"
        ]):
            scheme_text = recommend_schemes_for_user(user, message, lang)
            if not scheme_text:
                scheme_text = (
                    "At the moment no exact matching scheme is found for your profile, "
                    "but your nearest bank or CSC can check more detailed eligibility."
                )
            personalized_blocks.append(scheme_text)

        if 'save' in message_lower or 'saving' in message_lower:
            personalized_blocks.append(
                f"Your monthly income is about ₹{monthly_income:.0f} and expenses are ₹{monthly_expenses:.0f}, "
                f"so you save roughly ₹{savings:.0f} ({savings_rate:.1f}%).\n"
                "For you specifically:\n"
                "1) Set up an auto‑transfer into a savings/recurring deposit or PPF every month.\n"
                "2) Target a 10–15% cut in high‑spend categories such as entertainment or eating out."
            )

        if 'goal' in message_lower:
            goals = Goal.query.filter_by(user_id=user.user_id).all()
            if goals:
                goal_info = []
                for g in goals[:3]:
                    progress = (float(g.saved_amount) / float(g.target_amount) * 100) if g.target_amount else 0
                    goal_info.append(f"• {g.goal_name}: ₹{g.saved_amount}/{g.target_amount} ({progress:.0f}%)")
                personalized_blocks.append(
                    "Your existing financial goals:\n" + "\n".join(goal_info) +
                    "\n\nSeparate small SIPs/RDs for each goal will make tracking easier."
                )

        if not personalized_blocks:
            personalized_blocks.append(
                f"Given your profile (income ₹{monthly_income:.0f}, expenses ₹{monthly_expenses:.0f}, location {user.location}), "
                "consistent saving and the right schemes can significantly improve your financial health."
            )

    parts = []
    if base_rbi_part:
        parts.append(base_rbi_part)
    if base_scheme_part:
        parts.append("\n" + base_scheme_part)
    if lang == "hi":
        parts.append("\n\nअब आपकी प्रोफ़ाइल के आधार पर कुछ व्यक्तिगत सुझाव:\n")
    else:
        parts.append("\n\nNow some personalised suggestions based on your profile:\n")
    parts.append("\n\n".join(personalized_blocks))
    return "\n".join(parts)


# ==================== Authentication Routes ====================
@app.route('/verify-token', methods=['POST'])
def verify_token():
    """Verify Firebase ID token and create/login user"""
    print("\n" + "="*50)
    print("TOKEN VERIFICATION STARTED")
    print("="*50)
    
    try:
        # Get request data
        data = request.get_json()
        print(f"Request data received: {data is not None}")
        
        if not data:
            print("ERROR: No JSON data received")
            return jsonify({'error': 'No data received'}), 400
        
        id_token = data.get('idToken')
        if not id_token:
            print("ERROR: No idToken in request")
            return jsonify({'error': 'Missing ID token'}), 400
        
        print(f"Token received (first 50 chars): {id_token[:50]}...")
        print(f"Token length: {len(id_token)}")
        
        # Verify the token with Firebase Admin SDK
        print("Attempting to verify token with Firebase...")
        try:
            decoded_token = admin_auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            phone = decoded_token.get('phone_number', '').lstrip('+91')  # ✅ Clean phone
            
            print("✓ TOKEN VERIFIED SUCCESSFULLY!")
            print(f"  UID: {uid}")
            print(f"  Phone: {phone}")
            print(f"  Decoded token keys: {decoded_token.keys()}")
            
        except admin_auth.InvalidIdTokenError as e:
            print(f"✗ Invalid ID Token Error: {e}")
            return jsonify({'error': 'Invalid token', 'details': str(e)}), 401
        except admin_auth.ExpiredIdTokenError as e:
            print(f"✗ Expired ID Token Error: {e}")
            return jsonify({'error': 'Token expired', 'details': str(e)}), 401
        except admin_auth.RevokedIdTokenError as e:
            print(f"✗ Revoked ID Token Error: {e}")
            return jsonify({'error': 'Token revoked', 'details': str(e)}), 401
        except Exception as verify_error:
            print(f"✗ Token verification exception: {type(verify_error).__name__}")
            print(f"✗ Error details: {verify_error}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'Token verification failed', 'details': str(verify_error)}), 401
        
        # ✅ PHONE NUMBER LOOKUP (NEW!)
        print(f"\nChecking if user exists by PHONE NUMBER...")
        user = User.query.filter_by(phone_number=phone).first()
        
        if user:
            # ✅ EXISTING USER (synthetic + real) - straight to dashboard
            session['user_id'] = uid
            session['phone_number'] = phone           # ✅ ADDED
            session['db_user_id'] = user.user_id      # ✅ ADDED
            session['onboarding_complete'] = True
            
            print(f"✅ EXISTING USER FOUND: {user.name} (ID: {user.user_id})")  # ✅ Updated print
            
            return jsonify({
                'message': 'Login successful',
                'uid': uid,
                'user_exists': True,                      # ✅ ADDED
                'redirect': url_for('dashboard')          # ✅ Dashboard direct
            }), 200
        else:
            # ❌ NEW USER - onboarding required
            session['user_id'] = uid
            session['phone_number'] = phone            # ✅ Fixed key name
            session['onboarding_complete'] = False
            
            print(f"✓ NEW USER - REDIRECTING TO ONBOARDING")
            print(f"  UID stored in session: {session.get('user_id')}")
            print(f"  Phone: {phone}")
            
            return jsonify({
                'message': 'New user',
                'uid': uid,
                'user_exists': False,                     # ✅ ADDED
                'redirect': url_for('onboarding_user')
            }), 200
        
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR in verify_token:")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Server error', 'details': str(e)}), 500
    finally:
        print("="*50)
        print("TOKEN VERIFICATION ENDED")
        print("="*50 + "\n")

@app.route('/login', methods=['GET'])
def login():
    """Login page"""
    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang
    
    # If already logged in, redirect
    if 'user_id' in session and session.get('onboarding_complete'):
        return redirect(url_for('home'))
    
    return render_template('login.html', lang=lang)


@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect(url_for('login'))


# ==================== Onboarding Routes ====================
@app.route('/onboarding/user', methods=['GET', 'POST'])
def onboarding_user():
    """Step 1: User basic information"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang

    if request.method == 'POST':
        try:
            # Safely handle optional numeric fields
            total_loan_amount_raw = request.form.get('total_loan_amount')
            monthly_emi_total_raw = request.form.get('monthly_emi_total')

            user = User(
                firebase_uid=session['user_id'],
                phone_number=session['phone_number'],
                name=request.form.get('name'),
                age=int(request.form.get('age', 0)),
                gender=request.form.get('gender'),
                marital_status=request.form.get('marital_status'),
                education_level=request.form.get('education_level'),
                occupation=request.form.get('occupation'),
                sector=request.form.get('sector'),
                household_size=int(request.form.get('household_size', 1)),
                state=request.form.get('state'),
                city=request.form.get('city'),
                location_type=request.form.get('location_type'),
                location=request.form.get('location'),
                monthly_income=float(request.form.get('monthly_income', 0)),
                monthly_expenses=float(request.form.get('monthly_expenses', 0)),
                income_source_primary=request.form.get('income_source_primary'),
                has_irregular_income=request.form.get('has_irregular_income') == 'on',
                has_loans=request.form.get('has_loans') == 'on',
                total_loan_amount=float(total_loan_amount_raw) if total_loan_amount_raw else 0,
                monthly_emi_total=float(monthly_emi_total_raw) if monthly_emi_total_raw else 0,
                loan_type_primary=request.form.get('loan_type_primary'),
                existing_loans=request.form.get('existing_loans', ''),
                preferred_payment_mode=request.form.get('preferred_payment_mode'),
                financial_literacy_level=request.form.get('financial_literacy_level'),
                risk_tolerance=request.form.get('risk_tolerance')
            )
            db.session.add(user)
            db.session.commit()

            session['db_user_id'] = user.user_id
            return redirect(url_for('onboarding_transactions', lang=lang))

        except Exception as e:
            db.session.rollback()
            return render_template('onboarding_user.html', lang=lang, error=str(e))

    return render_template('onboarding_user.html', lang=lang)

@app.route('/onboarding/transactions', methods=['GET', 'POST'])
def onboarding_transactions():
    """Step 2: Transaction details"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang

    if request.method == 'POST':
        try:
            # Prefer db_user_id if set (from verify_token)
            db_user_id = session.get('db_user_id')
            if db_user_id:
                user = User.query.get(db_user_id)
            else:
                user = User.query.filter_by(firebase_uid=session['user_id']).first()

            if not user:
                return redirect(url_for('onboarding_user'))

            transactions = []
            for key in request.form.keys():
                if key.startswith('transactions-') and key.endswith('-date'):
                    idx = key.split('-')[1]
                    try:
                        date_str = request.form.get(f'transactions-{idx}-date')
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                        amount = float(request.form.get(f'transactions-{idx}-amount'))
                        typ = request.form.get(f'transactions-{idx}-type')
                        category = request.form.get(f'transactions-{idx}-category')
                        mode = request.form.get(f'transactions-{idx}-mode_of_payment')
                        notes = request.form.get(f'transactions-{idx}-notes', '')

                        txn = Transaction(
                            user_id=user.user_id,
                            date=date_obj,
                            amount=amount,
                            type=typ,
                            category=category,
                            mode_of_payment=mode,
                            notes=notes
                        )
                        transactions.append(txn)
                    except Exception:
                        continue

            if transactions:
                db.session.add_all(transactions)
                db.session.commit()

            return redirect(url_for('onboarding_goals', lang=lang))

        except Exception as e:
            db.session.rollback()
            print("TRANSACTION ERROR:", e)   # <-- add this
            return render_template('onboarding_transactions.html', lang=lang, error=str(e))


    return render_template('onboarding_transactions.html', lang=lang)


@app.route('/onboarding/goals', methods=['GET', 'POST'])
def onboarding_goals():
    """Step 3: Financial goals"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang
    
    if request.method == 'POST':
        try:
            phone = session.get('phone_number')
            if phone:
                user = User.query.filter_by(phone_number=phone).first()
            else:
                user = User.query.filter_by(firebase_uid=session['user_id']).first()

            if not user:
                return redirect(url_for('onboarding_user'))
            
            goals = []
            for key in request.form.keys():
                if key.startswith('goals-') and key.endswith('goal_name'):
                    idx = key.split('-')[1]
                    try:
                        goal_name = request.form.get(f'goals-{idx}-goal_name')
                        target_amount = float(request.form.get(f'goals-{idx}-target_amount'))
                        saved_amount = float(request.form.get(f'goals-{idx}-saved_amount', 0))
                        start_date = datetime.strptime(request.form.get(f'goals-{idx}-start_date'), '%Y-%m-%d').date()
                        deadline = datetime.strptime(request.form.get(f'goals-{idx}-deadline'), '%Y-%m-%d').date()
                        goal_type = request.form.get(f'goals-{idx}-goal_type')
                        priority = request.form.get(f'goals-{idx}-priority')
                        
                        goal = Goal(
                            user_id=user.user_id,
                            goal_name=goal_name,
                            target_amount=target_amount,
                            saved_amount=saved_amount,
                            start_date=start_date,
                            deadline=deadline,
                            goal_type=goal_type,
                            priority=priority
                        )
                        goals.append(goal)
                    except Exception:
                        continue
            
            if goals:
                db.session.add_all(goals)
                db.session.commit()
            
            # Mark onboarding as complete
            session['onboarding_complete'] = True
            return redirect(url_for('dashboard', lang=lang))
        
        except Exception as e:
            db.session.rollback()
            return render_template('onboarding_goals.html', lang=lang, error=str(e))
    
    return render_template('onboarding_goals.html', lang=lang)


# ==================== Main App Routes ====================
@app.route('/')
@app.route('/home')
def home():
    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang

    if 'user_id' in session and session.get('onboarding_complete'):
        phone = session.get('phone_number')
        if phone:
            user = User.query.filter_by(phone_number=phone).first()
        else:
            user = User.query.filter_by(firebase_uid=session['user_id']).first()
        return render_template('home.html', lang=lang, user=user, logged_in=True)

    return render_template('home.html', lang=lang, logged_in=False)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if not session.get('onboarding_complete'):
        return redirect(url_for('onboarding_user'))

    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang

    # Identify user
    phone = session.get('phone_number')
    if phone:
        user = User.query.filter_by(phone_number=phone).first()
    else:
        user = User.query.filter_by(firebase_uid=session['user_id']).first()

    if not user:
        return redirect(url_for('login'))

    # ---- 1) Financial metrics ----
    health_score, savings_rate, expense_ratio, monthly_income, monthly_expenses, savings = \
        compute_health_and_savings(user)

    # ---- 2) Goals + strict & soft recommendations ----
    goals = Goal.query.filter_by(user_id=user.user_id).all()
    goal_cards = []

    for g in goals:
        months_to_goal = estimate_months_to_goal(user, g)

        # NEW recommender (strict + soft lists)
        strict_recs, soft_recs = recommend_schemes_for_goal(
            user, g, top_n=5, soft_top_n=5
        )

        # Add both sets into goal_cards
        goal_cards.append({
            "goal": g,
            "strict_schemes": strict_recs,
            "soft_schemes": soft_recs,
            "months_to_goal": months_to_goal,
        })

    # ---- 3) Expense breakdown for pie chart ----
    expenses_data = (
        db.session.query(Transaction.category, func.sum(Transaction.amount))
        .filter(Transaction.user_id == user.user_id,
                Transaction.type == 'Expense')
        .group_by(Transaction.category)
        .all()
    )
    expense_categories = [row[0] for row in expenses_data]
    expense_amounts = [float(row[1]) for row in expenses_data]

    # ---- 3b) Monthly spend by category for year filter ----
    years_rows = (
        db.session.query(func.distinct(extract('year', Transaction.date)))
        .filter(Transaction.user_id == user.user_id,
                Transaction.type == 'Expense')
        .order_by(extract('year', Transaction.date))
        .all()
    )
    available_years = [int(y[0]) for y in years_rows] or [datetime.now().year]
    selected_year = request.args.get('year', type=int) or available_years[-1]

    monthly_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    rows = (
        db.session.query(
            extract('month', Transaction.date).label('m'),
            Transaction.category,
            func.sum(Transaction.amount).label('total')
        )
        .filter(
            Transaction.user_id == user.user_id,
            Transaction.type == 'Expense',
            extract('year', Transaction.date) == selected_year
        )
        .group_by('m', Transaction.category)
        .all()
    )

    spend_datasets = {}
    for m, cat, total in rows:
        cat_dict = spend_datasets.setdefault(cat, [0.0] * 12)
        cat_dict[int(m) - 1] = float(total)

    # ---- 4) Render dashboard ----
    return render_template(
        'dashboard.html',
        lang=lang,
        user=user,
        health_score=health_score,
        savings_rate=savings_rate,
        expense_ratio=expense_ratio,
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
        savings=savings,
        goal_cards=goal_cards,    # IMPORTANT: now includes strict + soft schemes
        expense_categories=expense_categories,
        expense_amounts=expense_amounts,
        available_years=available_years,
        selected_year=selected_year,
        monthly_labels=monthly_labels,
        spend_datasets=spend_datasets,
    )


@app.route('/schemes/<int:index>')
def scheme_detail(index):
    if index < 0 or index >= len(SCHEMES):
        return "Scheme not found", 404

    fields = SCHEMES[index].get("fields", {})
    return render_template(
        'scheme_detail.html',
        scheme=fields
    )

@app.route('/transactions')
def transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang

    # identify user
    phone = session.get('phone_number')
    if phone:
        user = User.query.filter_by(phone_number=phone).first()
    else:
        user = User.query.filter_by(firebase_uid=session['user_id']).first()

    if not user:
        return redirect(url_for('login'))

    user_transactions = (
        Transaction.query
        .filter_by(user_id=user.user_id)
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .all()
    )

    return render_template(
        'transactions.html',
        lang=lang,
        user=user,
        transactions=user_transactions,
    )

@app.route('/transactions/add', methods=['GET', 'POST'])
def add_transaction():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang

    # identify user
    phone = session.get('phone_number')
    if phone:
        user = User.query.filter_by(phone_number=phone).first()
    else:
        user = User.query.filter_by(firebase_uid=session['user_id']).first()

    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            txs = []
            for key in request.form.keys():
                # look for "transactions-<idx>-date"
                if key.startswith('transactions-') and key.endswith('-date'):
                    idx = key.split('-')[1]
                    try:
                        date_str = request.form.get(f'transactions-{idx}-date')
                        amount = float(request.form.get(f'transactions-{idx}-amount', 0))
                        tx_type = request.form.get(f'transactions-{idx}-type')
                        category = request.form.get(f'transactions-{idx}-category')
                        mode = request.form.get(f'transactions-{idx}-mode_of_payment')
                        notes = request.form.get(f'transactions-{idx}-notes')

                        tx = Transaction(
                            user_id=user.user_id,
                            date=datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date(),
                            amount=amount,
                            type=tx_type,
                            category=category,
                            mode_of_payment=mode,
                            notes=notes,
                        )
                        txs.append(tx)
                    except Exception:
                        continue

            if txs:
                db.session.add_all(txs)
                db.session.commit()

            return redirect(url_for('transactions'))

        except Exception as e:
            db.session.rollback()
            return render_template(
                'onboarding_transactions.html',
                lang=lang,
                error=str(e),
                simple_mode=True,
            )

    # GET
    return render_template('onboarding_transactions.html', lang=lang, simple_mode=True)

@app.route('/goals/add', methods=['GET', 'POST'])
def add_goal():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang

    # identify user
    phone = session.get('phone_number')
    if phone:
        user = User.query.filter_by(phone_number=phone).first()
    else:
        user = User.query.filter_by(firebase_uid=session['user_id']).first()

    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            goals = []
            for key in request.form.keys():
                if key.startswith('goals-') and key.endswith('goal_name'):
                    idx = key.split('-')[1]
                    try:
                        goal_name = request.form.get(f'goals-{idx}-goal_name')
                        target_amount = float(request.form.get(f'goals-{idx}-target_amount'))
                        saved_amount = float(request.form.get(f'goals-{idx}-saved_amount', 0))
                        start_date_str = request.form.get(f'goals-{idx}-start_date')
                        deadline_str = request.form.get(f'goals-{idx}-deadline')
                        goal_type = request.form.get(f'goals-{idx}-goal_type')
                        priority = request.form.get(f'goals-{idx}-priority')

                        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
                        deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date() if deadline_str else None

                        g = Goal(
                            user_id=user.user_id,
                            goal_name=goal_name,
                            target_amount=target_amount,
                            saved_amount=saved_amount,
                            start_date=start_date,
                            deadline=deadline,
                            goal_type=goal_type,
                            priority=priority,
                        )
                        goals.append(g)
                    except Exception:
                        continue

            if goals:
                db.session.add_all(goals)
                db.session.commit()

            return redirect(url_for('dashboard'))

        except Exception as e:
            db.session.rollback()
            return render_template('onboarding_goals.html', lang=lang, error=str(e), simple_mode=True)

    # GET
    return render_template('onboarding_goals.html', lang=lang, simple_mode=True)

@app.route('/chatbot')
def chatbot_page():
    """Dedicated chatbot page - accessible without login"""
    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang
    
    # Check if user is logged in
    logged_in = 'user_id' in session and session.get('onboarding_complete', False)
    
    return render_template('chatbot.html', lang=lang, logged_in=logged_in)

@app.route('/profile')
def profile():
    """User profile page"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if not session.get('onboarding_complete'):
        return redirect(url_for('onboarding_user'))
    
    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang

    # Identify user from session (same logic as dashboard/transactions)
    phone = session.get('phone_number')
    if phone:
        user = User.query.filter_by(phone_number=phone).first()
    else:
        user = User.query.filter_by(firebase_uid=session['user_id']).first()

    if not user:
        return redirect(url_for('login'))
    
    return render_template('profile.html', lang=lang, user=user)



@app.route('/api/update-profile', methods=['POST'])
def update_profile():
    """Update user profile"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        user = User.query.filter_by(firebase_uid=session['user_id']).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Update user fields
        user.name = data.get('name', user.name)
        user.age = int(data.get('age', user.age))
        user.gender = data.get('gender', user.gender)
        user.occupation = data.get('occupation', user.occupation)
        user.household_size = int(data.get('household_size', user.household_size))
        user.location = data.get('location', user.location)
        user.monthly_income = float(data.get('monthly_income', user.monthly_income))
        user.monthly_expenses = float(data.get('monthly_expenses', user.monthly_expenses))
        user.existing_loans = data.get('existing_loans', user.existing_loans)
        
        db.session.commit()
        
        return jsonify({'message': 'Profile updated successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Profile update error: {e}")
        return jsonify({'error': 'Update failed', 'details': str(e)}), 500



@app.route('/learning-hub')
def learning_hub():
    """Learning hub page - accessible without login"""
    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang
    
    return render_template('learning_hub.html', lang=lang)


# ==================== API Routes ====================


@app.route('/api/chat', methods=['POST'])
def chat():
    """Chatbot API endpoint - works for both logged-in and guest users"""
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        lang = data.get('lang', 'en')
        
        # Check if user is logged in
        if 'user_id' in session and session.get('onboarding_complete'):
            # Logged-in user - get personalized response
            user = User.query.filter_by(firebase_uid=session['user_id']).first()
            if user:
                bot_response = generate_ai_response(user_message, user, lang)
            else:
                bot_response = generate_guest_response(user_message, lang)
        else:
            # Guest user - provide general response
            bot_response = generate_guest_response(user_message, lang)
        
        return jsonify({
            'response': bot_response,
            'status': 'success'
        })
        
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500


# ==================== Error Handlers ====================
@app.route('/favicon.ico')
def favicon():
    """Serve favicon or return 204 if not found"""
    try:
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon'
        )
    except FileNotFoundError:
        return '', 204


@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors"""
    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang

    try:
        return render_template('404.html', lang=lang), 404
    except:
        # Fallback if template doesn't exist
        error_msg = "Page not found" if lang == 'en' else "पृष्ठ नहीं मिला"
        return f'''
        <html>
        <head>
            <title>404 - {error_msg}</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f8fbfd; }}
                h1 {{ color: #1793b8; font-size: 80px; margin: 0; }}
                p {{ color: #666; font-size: 20px; }}
                a {{ color: #1793b8; text-decoration: none; font-weight: bold; }}
            </style>
        </head>
        <body>
            <h1>404</h1>
            <p>{error_msg}</p>
            <a href="/">Go to Home</a>
        </body>
        </html>
        ''', 404


@app.errorhandler(500)
def internal_error(e):
    """Handle 500 errors"""
    lang = request.args.get('lang', session.get('lang', 'en'))
    session['lang'] = lang

    try:
        return render_template('500.html', lang=lang, error=str(e)), 500
    except:
        # Fallback if template doesn't exist
        error_msg = "Internal server error" if lang == 'en' else "आंतरिक सर्वर त्रुटि"
        return f'''
        <html>
        <head>
            <title>500 - {error_msg}</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f8fbfd; }}
                h1 {{ color: #dc2626; font-size: 80px; margin: 0; }}
                p {{ color: #666; font-size: 20px; }}
                a {{ color: #1793b8; text-decoration: none; font-weight: bold; }}
            </style>
        </head>
        <body>
            <h1>500</h1>
            <p>{error_msg}</p>
            <p style="color: #999; font-size: 14px;">{str(e)}</p>
            <a href="/">Go to Home</a>
        </body>
        </html>
        ''', 500

# ==================== Database Initialization ====================


def init_database():
    """Create database tables if they don't exist"""
    with app.app_context():
        try:
            db.create_all()
            print("✓ Database tables created successfully!")
        except Exception as e:
            print(f"✗ Database initialization error: {e}")


# Initialize database when the app starts
init_database()

# Add a custom Jinja filter for comma formatting
def comma_format(value):
    try:
        return "{:,}".format(int(value))
    except Exception:
        return value

app.jinja_env.filters['comma'] = comma_format


# ==================== Main ====================


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
